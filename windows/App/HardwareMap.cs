using System;
using System.Collections.Generic;
using System.Globalization;
using System.Management;
using System.Text;
using System.Text.RegularExpressions;

namespace A1401
{
    /// <summary>A read-only map of the identifiers that decide whether this PC's hardware is supported:
    /// the PCI, USB, HID and audio-codec numbers, and the ACPI device IDs. It is the Windows half of the
    /// map the Mac app produces, and it writes the SAME field names on purpose, so a map sent from a PC
    /// and a map sent from a Mac can be compared line for line when working out why a card is not driven.
    ///
    /// It changes nothing and reads nothing privileged. Every answer is a number taken from a device's
    /// hardware identifier, or a "...unavailable: reason" string. An absent field means the value could
    /// not be read - it never means the device is absent, and it never means supported.
    ///
    /// The rule that keeps this safe to send us, and it is a strict allow-list, not a filter:
    /// only the fields below are ever emitted, each masked to its own width, and every one of them comes
    /// from a fixed-width hexadecimal capture in a Windows identifier. Windows hands out far more than
    /// that. In particular a PNPDeviceID's LAST segment is an instance path, and for USB devices it is
    /// frequently the device's SERIAL NUMBER (USB\VID_046D&amp;PID_C52B\6&amp;1a2b3c4d&amp;0&amp;2). That segment is
    /// parsed for nothing and copied nowhere: every pattern here is anchored at the start of the string
    /// and stops before the instance path. Neither are friendly names, which users rename, nor MAC
    /// addresses, nor volume or machine identifiers, nor anything from a device's Name or Description.
    ///
    /// Why the class and usage numbers are worth carrying: a controller's PCI class code is what says
    /// "this is an HD-audio controller", and an HDAUDIO identifier is the only place Windows states the
    /// audio CODEC's own vendor and device. A report that lists a sound controller but no codec is the
    /// exact shape of the silent-audio fault, and without these two fields the map cannot show it.</summary>
    static class HardwareMap
    {
        // Each hardware-ID token maps to the field name the Mac app uses, with the mask that bounds it.
        // Keeping the names identical across both apps is the point: the two maps are read side by side.
        const int MaxDevices = 512;          // devices actually listed
        const int MaxExamined = 4096;        // devices looked at, listed or not - this is what bounds the loop
        const int MaxAcpiIDs = 64;

        // Same shapes the Mac app accepts: PNP####, ACPI####, and three- or four-letter vendor IDs.
        static readonly Regex AcpiShape = new Regex(
            @"^(?:PNP[0-9A-F]{4}|ACPI[0-9A-F]{4}|[A-Z]{3}[0-9A-F]{4}|[A-Z]{4}[0-9A-F]{4})$",
            RegexOptions.Compiled | RegexOptions.CultureInvariant);

        static readonly Regex Pci = new Regex(
            @"^PCI\\VEN_(?<ven>[0-9A-F]{4})&DEV_(?<dev>[0-9A-F]{4})(?:&SUBSYS_(?<sub>[0-9A-F]{8}))?(?:&REV_(?<rev>[0-9A-F]{2}))?",
            RegexOptions.Compiled | RegexOptions.CultureInvariant);

        static readonly Regex Usb = new Regex(
            @"^USB\\VID_(?<ven>[0-9A-F]{4})&PID_(?<dev>[0-9A-F]{4})(?:&REV_(?<rev>[0-9A-F]{4}))?(?:&MI_(?<mi>[0-9A-F]{2}))?",
            RegexOptions.Compiled | RegexOptions.CultureInvariant);

        static readonly Regex Hid = new Regex(
            @"^HID\\VID_(?<ven>[0-9A-F]{4})&PID_(?<dev>[0-9A-F]{4})",
            RegexOptions.Compiled | RegexOptions.CultureInvariant);

        // The audio codec. Windows states it ONLY here: the PCI device is the controller, and this is the
        // chip behind it (HDAUDIO\FUNC_01&VEN_10EC&DEV_0256&SUBSYS_10EC0256&REV_1001). The Mac app reads the
        // same pair as one 32-bit IOHDACodecVendorID, so it is packed the same way: vendor << 16 | device.
        static readonly Regex HdAudio = new Regex(
            @"^HDAUDIO\\(?:FUNC_(?<func>[0-9A-F]{2})&)?VEN_(?<ven>[0-9A-F]{4})&DEV_(?<dev>[0-9A-F]{4})(?:&SUBSYS_(?<sub>[0-9A-F]{8}))?(?:&REV_(?<rev>[0-9A-F]{4}))?",
            RegexOptions.Compiled | RegexOptions.CultureInvariant);

        // Class numbers live in a device's CompatibleID list, not in its hardware ID.
        // PCI\VEN_10DE&CC_040300 or PCI\CC_0403: six digits are class/subclass/prog-if, four are class/subclass.
        static readonly Regex PciClass = new Regex(
            @"^PCI\\(?:VEN_[0-9A-F]{4}&)?CC_(?<cc>[0-9A-F]{4}(?:[0-9A-F]{2})?)$",
            RegexOptions.Compiled | RegexOptions.CultureInvariant);

        // USB\Class_03&SubClass_01&Prot_01 - on an interface device these are the interface's numbers.
        static readonly Regex UsbClass = new Regex(
            @"^USB\\(?:DEV)?CLASS_(?<cls>[0-9A-F]{2})(?:&SUBCLASS_(?<sub>[0-9A-F]{2}))?(?:&PROT_(?<prot>[0-9A-F]{2}))?$",
            RegexOptions.Compiled | RegexOptions.CultureInvariant);

        // HID_DEVICE_UP:000C_U:0001 - the top-level usage page and usage of a HID collection.
        static readonly Regex HidUsage = new Regex(
            @"^HID_DEVICE_UP:(?<page>[0-9A-F]{4})_U:(?<usage>[0-9A-F]{4})$",
            RegexOptions.Compiled | RegexOptions.CultureInvariant);

        static bool Hex(string text, out ulong value)
        {
            value = 0;
            return !string.IsNullOrEmpty(text)
                && ulong.TryParse(text, NumberStyles.HexNumber, CultureInfo.InvariantCulture, out value);
        }

        /// <summary>The identifier numbers of one device, or an empty set when its ID is not a shape we
        /// read. The instance segment is never examined: see the warning on the class.</summary>
        internal static Dictionary<string, ulong> Facts(string pnpDeviceID)
        {
            var found = new Dictionary<string, ulong>();
            if (string.IsNullOrEmpty(pnpDeviceID)) return found;
            // Hardware IDs are case-insensitive in practice; the patterns are written upper-case.
            string id = pnpDeviceID.ToUpperInvariant();
            ulong n;

            Match m = Pci.Match(id);
            if (m.Success)
            {
                if (Hex(m.Groups["ven"].Value, out n)) found["pci_vendor"] = n & 0xffff;
                if (Hex(m.Groups["dev"].Value, out n)) found["pci_device"] = n & 0xffff;
                if (m.Groups["sub"].Success && Hex(m.Groups["sub"].Value, out n))
                {
                    // SUBSYS packs the subsystem device in the high half and the vendor in the low half,
                    // which is the opposite order to how it reads.
                    found["pci_subsystem_device"] = (n >> 16) & 0xffff;
                    found["pci_subsystem_vendor"] = n & 0xffff;
                }
                if (m.Groups["rev"].Success && Hex(m.Groups["rev"].Value, out n)) found["pci_revision"] = n & 0xff;
                return found;
            }
            m = HdAudio.Match(id);
            if (m.Success)
            {
                ulong vendor, device;
                if (Hex(m.Groups["ven"].Value, out vendor) && Hex(m.Groups["dev"].Value, out device))
                    found["audio_codec_vendor_device"] = ((vendor & 0xffff) << 16) | (device & 0xffff);
                if (m.Groups["rev"].Success && Hex(m.Groups["rev"].Value, out n))
                    found["audio_codec_revision"] = n & 0xffffffff;
                if (m.Groups["func"].Success && Hex(m.Groups["func"].Value, out n))
                    found["audio_codec_function_group"] = n & 0xff;
                return found;
            }
            m = Usb.Match(id);
            if (m.Success)
            {
                if (Hex(m.Groups["ven"].Value, out n)) found["usb_vendor"] = n & 0xffff;
                if (Hex(m.Groups["dev"].Value, out n)) found["usb_product"] = n & 0xffff;
                // MI_xx is the interface number, and it is part of the ID, not of the instance path:
                // USB\VID_046D&PID_C52B&MI_01\8&1a2b3c4d&0&0000 - the serial is still only in the tail.
                if (m.Groups["mi"].Success && Hex(m.Groups["mi"].Value, out n))
                    found["usb_interface_number"] = n & 0xff;
                return found;
            }
            m = Hid.Match(id);
            if (m.Success)
            {
                if (Hex(m.Groups["ven"].Value, out n)) found["hid_vendor"] = n & 0xffff;
                if (Hex(m.Groups["dev"].Value, out n)) found["hid_product"] = n & 0xffff;
            }
            return found;
        }

        /// <summary>The class, subclass and usage numbers of one device. Windows puts these in the
        /// CompatibleID list rather than in the hardware ID, so they are read from there. Only whole
        /// fixed-width hexadecimal fields of an exactly-matching pattern are accepted, so nothing that is
        /// not one of these numbers can reach a field.</summary>
        internal static Dictionary<string, ulong> Classes(IEnumerable<string> compatibleIDs)
        {
            var found = new Dictionary<string, ulong>();
            if (compatibleIDs == null) return found;
            ulong n;
            foreach (string raw in compatibleIDs)
            {
                if (string.IsNullOrEmpty(raw) || raw.Length > 256) continue;
                string text = raw.ToUpperInvariant();

                Match m = PciClass.Match(text);
                if (m.Success && Hex(m.Groups["cc"].Value, out n))
                {
                    // CC_040300 is class 04 subclass 03 prog-if 00; CC_0403 is the same without prog-if.
                    // The Mac app's pci_class is the 24-bit value, so a four-digit form is shifted to match
                    // and the prog-if byte reads 0 - which is what Windows itself leaves unstated.
                    ulong code = m.Groups["cc"].Value.Length == 4 ? (n & 0xffff) << 8 : n & 0xffffff;
                    // Keep the widest statement: a six-digit form is more specific than a four-digit one.
                    ulong had;
                    if (!found.TryGetValue("pci_class", out had) || code > had) found["pci_class"] = code;
                    continue;
                }
                m = UsbClass.Match(text);
                if (m.Success)
                {
                    if (Hex(m.Groups["cls"].Value, out n)) found["usb_class"] = n & 0xff;
                    if (m.Groups["sub"].Success && Hex(m.Groups["sub"].Value, out n)) found["usb_subclass"] = n & 0xff;
                    if (m.Groups["prot"].Success && Hex(m.Groups["prot"].Value, out n)) found["usb_protocol"] = n & 0xff;
                    continue;
                }
                m = HidUsage.Match(text);
                if (m.Success)
                {
                    if (Hex(m.Groups["page"].Value, out n)) found["hid_usage_page"] = n & 0xffff;
                    if (Hex(m.Groups["usage"].Value, out n)) found["hid_usage"] = n & 0xffff;
                }
            }
            return found;
        }

        /// <summary>The ACPI device IDs of one device, kept only when they match the shapes the Mac app
        /// accepts. A CompatibleID list is where an ACPI name appears on Windows.
        ///
        /// Only a CompatibleID list is ever passed here, never a DeviceID. That is what makes taking the
        /// last segment safe: a CompatibleID states a device class or an ACPI name, while it is a
        /// DeviceID whose last segment can be a serial number.</summary>
        internal static List<string> AcpiIDs(IEnumerable<string> compatibleIDs)
        {
            var kept = new SortedSet<string>(StringComparer.Ordinal);
            if (compatibleIDs == null) return new List<string>();
            foreach (string raw in compatibleIDs)
            {
                if (kept.Count >= MaxAcpiIDs || string.IsNullOrEmpty(raw) || raw.Length > 256) continue;
                string text = raw.ToUpperInvariant();
                // ACPI\PNP0A08 and *PNP0A08 both occur; take the last segment either way.
                int cut = text.LastIndexOfAny(new[] { '\\', '*' });
                if (cut >= 0) text = text.Substring(cut + 1);
                if (AcpiShape.IsMatch(text)) kept.Add(text);
            }
            return new List<string>(kept);
        }

        /// <summary>A device is worth a line when it carries at least one identifier we read. Devices with
        /// nothing readable are counted, not listed, so the map stays about hardware identity.</summary>
        internal static bool Relevant(Dictionary<string, ulong> facts, List<string> acpi)
        {
            return (facts != null && facts.Count > 0) || (acpi != null && acpi.Count > 0);
        }

        /// <summary>One device's line. The fields are written in name order so that two maps of the same
        /// PC are the same text, and two maps of different PCs differ only where the hardware does - a map
        /// whose field order moved between runs cannot be diffed, which is the only thing it is for.</summary>
        internal static string Line(Dictionary<string, ulong> facts, List<string> acpi)
        {
            var names = new List<string>(facts.Keys);
            names.Sort(StringComparer.Ordinal);
            var line = new StringBuilder("device");
            foreach (string name in names)
                line.Append(" ").Append(name).Append("=").Append(facts[name].ToString(CultureInfo.InvariantCulture));
            if (acpi != null && acpi.Count > 0) line.Append(" acpi_ids=").Append(string.Join(",", acpi.ToArray()));
            return line.ToString();
        }

        /// <summary>The whole map, as the lines the report carries. Any failure is reported as a line
        /// rather than thrown: a map that stops at the first unreadable device is worth less than one that
        /// says which part it could not read.</summary>
        public static string Collect()
        {
            var text = new StringBuilder();
            text.AppendLine("hardware map 1");
            int listed = 0, silent = 0, examined = 0;
            try
            {
                // Win32_PnPEntity is the whole device tree. Only DeviceID and CompatibleID are selected:
                // Name, Description and the rest are user-visible strings we have no reason to carry.
                using (var search = new ManagementObjectSearcher(
                    "SELECT DeviceID, CompatibleID FROM Win32_PnPEntity"))
                using (ManagementObjectCollection devices = search.Get())
                {
                    foreach (ManagementBaseObject device in devices)
                    {
                        // Every WMI object is a COM wrapper; 512 of them left undisposed is 512 handles
                        // held until a collection the scan step does not wait for.
                        using (device)
                        {
                            if (listed >= MaxDevices) { text.AppendLine("devices_truncated: " + MaxDevices); break; }
                            // The listed cap alone does not bound this loop: a PC whose devices are all
                            // unreadable would walk the whole tree without ever reaching it.
                            if (++examined > MaxExamined) { text.AppendLine("devices_examined_truncated: " + MaxExamined); break; }
                            string id;
                            List<string> acpi;
                            Dictionary<string, ulong> facts;
                            try
                            {
                                id = device["DeviceID"] as string;
                                var compatible = device["CompatibleID"] as string[];
                                acpi = AcpiIDs(compatible);
                                facts = Facts(id);
                                foreach (var pair in Classes(compatible))
                                    if (!facts.ContainsKey(pair.Key)) facts[pair.Key] = pair.Value;
                            }
                            catch (ManagementException)
                            {
                                silent++;
                                continue;
                            }
                            if (!Relevant(facts, acpi)) { silent++; continue; }
                            text.AppendLine(Line(facts, acpi));
                            listed++;
                        }
                    }
                }
            }
            catch (ManagementException error)
            {
                // Not "no devices": WMI itself did not answer. Saying so is the whole point of the line.
                text.AppendLine("devices_status: unavailable: " + error.GetType().Name);
            }
            catch (UnauthorizedAccessException)
            {
                text.AppendLine("devices_status: unavailable: access denied");
            }
            catch (Exception error)
            {
                // A PC whose WMI repository is damaged throws COMException or InvalidOperationException out
                // of Get() or out of the enumerator, neither of which is a ManagementException. Reporting
                // the type keeps the rule this file is built on: a check that could not run says so, and
                // never reads as a clean result.
                text.AppendLine("devices_status: unavailable: " + error.GetType().Name);
            }
            text.AppendLine("devices_listed: " + listed.ToString(CultureInfo.InvariantCulture));
            text.AppendLine("devices_without_identifiers: " + silent.ToString(CultureInfo.InvariantCulture));
            return text.ToString();
        }

        /// <summary>Writes the map beside the scan's other files and returns the one line worth showing.
        /// It is written as its own file rather than folded into Report.json so that a person can read it
        /// before sending it: the whole value of this map is that someone can see exactly what it says
        /// about their machine. A failure to write is reported, not thrown - the scan it rides along with
        /// is worth more than the map.</summary>
        public static string WriteTo(string directory)
        {
            string map;
            try
            {
                map = Collect();
            }
            catch (Exception error)
            {
                return Loc.F("Hardware map: not collected ({0}).", error.GetType().Name);
            }
            int devices = 0;
            foreach (string line in map.Split('\n'))
                if (line.StartsWith("device ", StringComparison.Ordinal)) devices++;
            try
            {
                string path = System.IO.Path.Combine(directory, "hardware-map.txt");
                System.IO.File.WriteAllText(path, map);
                return Loc.F("Hardware map: {0} device(s) with identifiers, written to hardware-map.txt.",
                             devices.ToString(CultureInfo.InvariantCulture));
            }
            catch (System.IO.IOException error)
            {
                return Loc.F("Hardware map: read {0} device(s) but could not save it ({1}).",
                             devices.ToString(CultureInfo.InvariantCulture), error.GetType().Name);
            }
            catch (UnauthorizedAccessException)
            {
                return Loc.F("Hardware map: read {0} device(s) but could not save it (access denied).",
                             devices.ToString(CultureInfo.InvariantCulture));
            }
        }
    }
}
