using System;
using System.Diagnostics;
using System.Management;
using System.Runtime.InteropServices;
using Microsoft.Win32;

namespace A1401
{
    /// <summary>What this PC is and the three things that decide whether the stick will boot:
    /// UEFI (the stick is UEFI-only), Secure Boot (must be off: the scanner is not Microsoft-signed),
    /// and BitLocker (turning Secure Boot off makes Windows ask for the recovery key next start).</summary>
    class SystemInfo
    {
        public string Firmware = "unknown";     // UEFI | BIOS | unknown
        public string SecureBoot = "unknown";   // on | off | unknown
        public string BitLocker = "unknown";    // on | off | unknown (+ reason)
        public string Maker = "", Model = "", BoardMaker = "", BoardName = "";
    }

    static class SystemChecks
    {
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool GetFirmwareType(out uint firmwareType);

        public static SystemInfo Read()
        {
            var s = new SystemInfo();
            try
            {
                uint t;
                if (GetFirmwareType(out t)) s.Firmware = t == 2 ? "UEFI" : (t == 1 ? "BIOS" : "unknown");
            }
            catch (Exception e) { s.Firmware = "unknown (" + e.Message + ")"; }

            try
            {
                using (var k = Registry.LocalMachine.OpenSubKey(@"SYSTEM\CurrentControlSet\Control\SecureBoot\State"))
                {
                    object v = k == null ? null : k.GetValue("UEFISecureBootEnabled");
                    if (v is int) s.SecureBoot = (int)v == 1 ? "on" : "off";
                    else if (s.Firmware == "BIOS") s.SecureBoot = "off";
                }
            }
            catch (Exception e) { s.SecureBoot = "unknown (" + e.Message + ")"; }

            try
            {
                var scope = new ManagementScope(@"\\.\root\CIMV2\Security\MicrosoftVolumeEncryption");
                string sys = Environment.GetEnvironmentVariable("SystemDrive") ?? "C:";
                using (var q = new ManagementObjectSearcher(scope, new ObjectQuery(
                    "SELECT DriveLetter, ProtectionStatus FROM Win32_EncryptableVolume")))
                {
                    s.BitLocker = "off";
                    foreach (ManagementObject o in q.Get())
                    {
                        string letter = (o["DriveLetter"] as string) ?? "";
                        if (!letter.Equals(sys, StringComparison.OrdinalIgnoreCase)) continue;
                        uint ps = Convert.ToUInt32(o["ProtectionStatus"]);
                        s.BitLocker = ps == 1 ? "on" : (ps == 0 ? "off" : "unknown");
                    }
                }
            }
            catch (ManagementException e) when (e.ErrorCode == ManagementStatus.InvalidNamespace)
            {
                s.BitLocker = "off";  // this Windows edition has no BitLocker/device encryption at all
            }
            catch (Exception e) { s.BitLocker = "unknown (" + e.Message + ")"; }

            try
            {
                foreach (ManagementObject o in new ManagementObjectSearcher("SELECT Manufacturer, Model FROM Win32_ComputerSystem").Get())
                { s.Maker = ("" + o["Manufacturer"]).Trim(); s.Model = ("" + o["Model"]).Trim(); }
                foreach (ManagementObject o in new ManagementObjectSearcher("SELECT Manufacturer, Product FROM Win32_BaseBoard").Get())
                { s.BoardMaker = ("" + o["Manufacturer"]).Trim(); s.BoardName = ("" + o["Product"]).Trim(); }
            }
            catch (Exception) { /* names only improve the boot-key hint; the hint falls back to the generic list */ }
            return s;
        }

        /// <summary>The one-time boot menu key for this maker, or null. Board maker first: a custom-built PC
        /// reports "To Be Filled By O.E.M." as the computer maker and the real vendor on the board.</summary>
        public static string BootKey(SystemInfo s)
        {
            string m = (s.BoardMaker + " " + s.Maker).ToUpperInvariant();
            if (m.Contains("ASUS")) return "F8";
            if (m.Contains("MICRO-STAR") || m.Contains("MSI")) return "F11";
            if (m.Contains("GIGABYTE")) return "F12";
            if (m.Contains("ASROCK")) return "F11";
            if (m.Contains("DELL") || m.Contains("ALIENWARE")) return "F12";
            if (m.Contains("HEWLETT") || m.Contains("HP ")) return "F9";
            if (m.Contains("LENOVO")) return "F12 (or the Novo button)";
            if (m.Contains("ACER")) return "F12";
            if (m.Contains("MICROSOFT")) return "hold Volume Down while pressing Power";
            if (m.Contains("SAMSUNG")) return "F2 then Boot tab";
            if (m.Contains("BIOSTAR")) return "F9";
            if (m.Contains("EVGA")) return "F7";
            if (m.Contains("SUPERMICRO")) return "F11";
            if (m.Contains("INTEL")) return "F10";
            return null;
        }

        /// <summary>Runs a Windows tool and returns (exit code, output). Every call is bounded.</summary>
        public static Tuple<int, string> Run(string exe, string args, int timeoutMs = 120000)
        {
            var psi = new ProcessStartInfo(exe, args)
            {
                UseShellExecute = false, CreateNoWindow = true,
                RedirectStandardOutput = true, RedirectStandardError = true
            };
            using (var p = Process.Start(psi))
            {
                var outTask = p.StandardOutput.ReadToEndAsync();
                var errTask = p.StandardError.ReadToEndAsync();
                if (!p.WaitForExit(timeoutMs))
                {
                    try { p.Kill(); } catch (Exception) { }
                    return Tuple.Create(-1, exe + " did not finish in " + timeoutMs / 1000 + " s");
                }
                return Tuple.Create(p.ExitCode, outTask.Result + errTask.Result);
            }
        }

        public static string Sys32(string exe)
        {
            return System.IO.Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), exe);
        }
    }
}
