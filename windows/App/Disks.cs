using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Management;
using System.Security.Cryptography;
using System.Text;
using System.Threading;

namespace A1401
{
    class UsbDisk
    {
        public uint Number;
        public string Name = "", UniqueId = "";
        public ulong Size;
        public string Letters = "";

        public override string ToString()
        {
            return string.Format("Disk {0}:  {1}  -  {2:0.#} GB{3}", Number, Name, Size / 1e9,
                Letters.Length > 0 ? "   (" + Letters + ")" : "");
        }
    }

    /// <summary>Finds USB sticks and turns one into the 1401 Probe stick.
    /// The only disks ever offered are BusType USB and not the system or boot disk, and the disk is
    /// re-identified by its UniqueId immediately before diskpart runs: a disk number can move when
    /// another drive is plugged in between choosing and wiping.</summary>
    static class Disks
    {
        const string StorageNs = @"\\.\root\Microsoft\Windows\Storage";
        public const string Label = "PROBE1401";
        const ushort BusTypeUsb = 7;

        // MSFT_Disk BusType numbers, so a disk that was left out can be named in words
        static string BusName(ushort b)
        {
            switch (b) { case 1: return "SCSI"; case 3: return "ATA"; case 7: return "USB"; case 8: return "RAID"; case 11: return "SATA";
                case 12: return "SD card"; case 13: return "MMC card"; case 17: return "NVMe"; default: return "bus " + b; }
        }

        /// <summary>`skipped`, when given, gets one line per disk that was left out and why, so "no stick found" can say what it saw.</summary>
        public static List<UsbDisk> ListUsb(List<string> skipped = null)
        {
            var list = new List<UsbDisk>();
            var scope = new ManagementScope(StorageNs);
            using (var q = new ManagementObjectSearcher(scope, new ObjectQuery(
                "SELECT Number, FriendlyName, Size, BusType, IsSystem, IsBoot, UniqueId FROM MSFT_Disk")))
            {
                foreach (ManagementObject o in q.Get())
                {
                    var bus = Convert.ToUInt16(o["BusType"]);
                    var what = "Disk " + o["Number"] + " " + ("" + o["FriendlyName"]).Trim() + string.Format(" ({0:0.#} GB)", Convert.ToUInt64(o["Size"]) / 1e9);
                    if (bus != BusTypeUsb) { if (skipped != null) skipped.Add(what + ": connected by " + BusName(bus) + ", not USB"); continue; }
                    if (Convert.ToBoolean(o["IsSystem"]) || Convert.ToBoolean(o["IsBoot"])) { if (skipped != null) skipped.Add(what + ": Windows runs from it"); continue; }
                    var d = new UsbDisk
                    {
                        Number = Convert.ToUInt32(o["Number"]),
                        Name = ("" + o["FriendlyName"]).Trim(),
                        Size = Convert.ToUInt64(o["Size"]),
                        UniqueId = "" + o["UniqueId"]
                    };
                    d.Letters = LettersOf(scope, d.Number);
                    list.Add(d);
                }
            }
            return list.OrderBy(d => d.Number).ToList();
        }

        static string LettersOf(ManagementScope scope, uint disk)
        {
            var letters = new List<string>();
            using (var q = new ManagementObjectSearcher(scope, new ObjectQuery(
                "SELECT DriveLetter FROM MSFT_Partition WHERE DiskNumber = " + disk)))
            {
                foreach (ManagementObject o in q.Get())
                {
                    char c = Convert.ToChar(o["DriveLetter"]);
                    if (char.IsLetter(c)) letters.Add(c + ":");
                }
            }
            return string.Join(" ", letters);
        }

        static char FreeLetter()
        {
            var used = new HashSet<char>(DriveInfo.GetDrives().Select(d => char.ToUpperInvariant(d.Name[0])));
            for (char c = 'Z'; c >= 'G'; c--) if (!used.Contains(c)) return c;
            throw new Exception("No free drive letter between G: and Z:.");
        }

        /// <summary>Wipe `disk`, make one FAT32 partition labelled PROBE1401, copy the payload, verify it.
        /// `say` reports progress (0-100, text). Throws with the reason on any failure.</summary>
        public static void MakeProbeStick(UsbDisk disk, string payload, Action<int, string> say)
        {
            say(2, "Checking the stick is still the one you picked...");
            var now = ListUsb().FirstOrDefault(d => d.Number == disk.Number);
            if (now == null || now.UniqueId != disk.UniqueId || now.Size != disk.Size)
                throw new Exception("The USB disk list changed since you picked a stick. Nothing was erased. Go back and pick it again.");
            if (!File.Exists(Path.Combine(payload, "SHA256SUMS")))
                throw new Exception("The scanner files are missing next to this app (" + payload + "). Reinstall 1401 Probe.");

            char letter = FreeLetter();
            // Windows' own FAT32 formatter refuses volumes over 32 GB, so big sticks get a 30 GB partition
            string size = disk.Size > 32000000000UL ? " size=30000" : "";
            string script = string.Join("\r\n", new[] {
                "select disk " + disk.Number, "clean", "convert mbr",
                "create partition primary" + size, "format fs=fat32 quick label=" + Label,
                "active", "assign letter=" + letter, "exit" }) + "\r\n";
            say(5, "Erasing and formatting the stick (this takes up to a minute)...");
            var r = Diskpart(script);
            // This used to check exit 0 and the output containing "successfully formatted", but diskpart speaks the Windows display language,
            // so every non-English PC failed here after a good format. The contract is /s mode's exit code (0 = every command
            // ran; 6 = one failed and diskpart stopped). The proof the format landed is language-neutral, below.
            if (r.Item1 != 0)
                throw new Exception("Windows could not format the stick (diskpart exit " + r.Item1 + "):\r\n\r\n" + Tail(r.Item2, 1200));

            string root = letter + @":\";
            for (int i = 0; i < 30 && !Directory.Exists(root); i++) Thread.Sleep(500);
            if (!Directory.Exists(root)) throw new Exception("The stick was formatted but " + root + " did not appear.");
            // the letter we assigned must read back as FAT32 with our label: file-system names and labels are not translated
            string fs = "?", vl = "?";
            try { var di = new DriveInfo(root); fs = di.DriveFormat; vl = di.VolumeLabel; }
            catch (IOException e) { fs = e.Message; }
            if (fs != "FAT32" || !string.Equals(vl, Label, StringComparison.OrdinalIgnoreCase))
                throw new Exception("The stick was formatted but " + root + " reads as " + fs + " labelled \"" + vl +
                    "\", not FAT32 labelled " + Label + ". Nothing was copied. Try again, or try a different stick.");

            var files = Directory.GetFiles(payload, "*", SearchOption.AllDirectories);
            long total = files.Sum(f => new FileInfo(f).Length), done = 0;
            var buf = new byte[4 << 20];
            foreach (var f in files)
            {
                string rel = f.Substring(payload.Length).TrimStart('\\', '/');
                string dst = Path.Combine(root, rel);
                Directory.CreateDirectory(Path.GetDirectoryName(dst));
                using (var i = File.OpenRead(f))
                using (var o = new FileStream(dst, FileMode.Create, FileAccess.Write, FileShare.None, 1 << 20, FileOptions.WriteThrough))
                {
                    int n;
                    while ((n = i.Read(buf, 0, buf.Length)) > 0)
                    {
                        o.Write(buf, 0, n);
                        done += n;
                        say(10 + (int)(75 * done / Math.Max(1, total)), "Copying the scanner: " + rel);
                    }
                }
            }
            Directory.CreateDirectory(Path.Combine(root, "REPORTS"));

            say(88, "Checking every file read back correctly...");
            Verify(root);
            say(100, "Done. The stick is ready.");
        }

        /// <summary>Re-reads every file listed in SHA256SUMS from the stick and compares the hash.</summary>
        public static void Verify(string root)
        {
            foreach (var line in File.ReadAllLines(Path.Combine(root, "SHA256SUMS")))
            {
                var parts = line.Split(new[] { ' ' }, 2, StringSplitOptions.RemoveEmptyEntries);
                if (parts.Length != 2) continue;
                string rel = parts[1].Trim().TrimStart('*').Replace('/', '\\');
                string p = Path.Combine(root, rel);
                if (!File.Exists(p)) throw new Exception("Missing on the stick after copying: " + rel);
                string h;
                using (var sha = SHA256.Create())
                using (var s = File.OpenRead(p))
                    h = BitConverter.ToString(sha.ComputeHash(s)).Replace("-", "").ToLowerInvariant();
                if (h != parts[0].ToLowerInvariant())
                    throw new Exception("A file on the stick does not match what was written: " + rel +
                        "\r\nThe stick may be failing. Try a different one.");
            }
        }

        /// <summary>Give the stick back as an ordinary exFAT drive (after the report has been saved elsewhere).</summary>
        public static void Reformat(UsbDisk disk, Action<int, string> say)
        {
            var now = ListUsb().FirstOrDefault(d => d.Number == disk.Number);
            if (now == null || now.UniqueId != disk.UniqueId)
                throw new Exception("The USB disk list changed. Nothing was erased.");
            say(20, "Erasing and formatting...");
            var r = Diskpart("select disk " + disk.Number + "\r\nclean\r\nconvert mbr\r\ncreate partition primary\r\n" +
                "format fs=exfat quick label=USB\r\nassign\r\nexit\r\n");
            if (r.Item1 != 0) throw new Exception("diskpart exit " + r.Item1 + ":\r\n" + Tail(r.Item2, 1200));
            say(100, "Done. The stick is an ordinary USB drive again.");
        }

        /// <summary>Runs a diskpart script from a file that nothing else can change while diskpart reads it.</summary>
        static Tuple<int, string> Diskpart(string script)
        {
            // This used to be a fixed-name file (%TEMP%\1401probe-diskpart.txt) written, then run with /s. %TEMP% belongs to the
            // unelevated user, so any program of theirs could rewrite "select disk N" between our write and diskpart's
            // read and aim "clean" at the system disk with our admin rights. Now: a random name made with CreateNew (a
            // planted file or link of that name fails it), re-opened with share Read only (no one else can open it for
            // write, delete or rename while we hold it), read back through that handle and compared, held until diskpart
            // exits. /s stays (not stdin): in /s mode diskpart stops at the first error with a real exit code.
            string sp = Path.Combine(Path.GetTempPath(), "1401probe-" + Guid.NewGuid().ToString("N") + ".txt");
            byte[] want = Encoding.ASCII.GetBytes(script);
            using (var w = new FileStream(sp, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                w.Write(want, 0, want.Length);
            try
            {
                using (var held = new FileStream(sp, FileMode.Open, FileAccess.Read, FileShare.Read))
                {
                    var got = new byte[want.Length + 1];
                    int n = 0, k;
                    while (n < got.Length && (k = held.Read(got, n, got.Length - n)) > 0) n += k;
                    if (n != want.Length || !got.Take(n).SequenceEqual(want))
                        throw new Exception("Another program changed the disk instructions before Windows ran them. Nothing was erased.");
                    return SystemChecks.Run(SystemChecks.Sys32("diskpart.exe"), "/s \"" + sp + "\"", 300000);
                }
            }
            finally
            {
                // a leftover script is a few harmless bytes; it must never turn a finished format into an error
                try { File.Delete(sp); } catch (IOException) { } catch (UnauthorizedAccessException) { }
            }
        }

        static string Tail(string s, int n) { return s.Length <= n ? s : "..." + s.Substring(s.Length - n); }
    }
}
