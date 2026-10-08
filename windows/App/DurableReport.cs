using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;

namespace A1401
{
    // Local diagnostic files survive restart and upload failure. Saving never sends a report.
    static class DurableReport
    {
        internal const int MaxCharacters = 500000;
        internal sealed class Outcome
        {
            internal string Path, Failure;
            internal bool Saved { get { return Path != null; } }
        }
        internal static string Clean(string value)
        {
            return CleanIdentity(value, Environment.UserName, Environment.MachineName,
                Environment.GetFolderPath(Environment.SpecialFolder.UserProfile));
        }

        // Explicit fields and home paths retain their privacy meaning even when an account shares a vendor word.
        internal static string CleanIdentity(string value, string user, string host, string home)
        {
            value = value ?? "";
            if (!string.IsNullOrEmpty(home) && home.Length > 3)
            {
                value = Regex.Replace(value, Regex.Escape(home.Replace("\\", "\\\\")), "%USERPROFILE%", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);
                value = Regex.Replace(value, Regex.Escape(home), "%USERPROFILE%", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);
            }
            value = Regex.Replace(value, @"(?i)[a-z]:(?:\\{1,2}|/)Users(?:\\{1,2}|/)[^\\/\r\n""\t]+", "%USERPROFILE%");
            var identities = new[] { new[] { user, "user", "user(?:name)?|account|login" },
                                     new[] { host, "this-pc", "host(?:name)?|computer(?: name)?|machine(?: name)?|pc" } };
            foreach (var identity in identities)
            {
                var name = identity[0];
                if (string.IsNullOrEmpty(name) || name.Length > 256) continue;
                var escaped = Regex.Escape(name);
                var fields = @"(?i)(\b(?:" + identity[2] + @")\b[""']?\s*(?:[:=]\s*[""']?|\s+))" + escaped + @"(?![\p{L}\p{N}_.-])";
                value = Regex.Replace(value, fields, m => m.Groups[1].Value + identity[1], RegexOptions.CultureInvariant);
                if (identity[1] == "this-pc")
                {
                    value = Regex.Replace(value, @"(\\{2,4})" + escaped + @"(?=\\)", m => m.Groups[1].Value + identity[1], RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);
                    value = Regex.Replace(value, @"(https?://)" + escaped + @"(?=[/:?#]|$)", m => m.Groups[1].Value + identity[1], RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);
                }
            }
            foreach (var identity in identities)
            {
                var name = identity[0];
                if (string.IsNullOrEmpty(name) || name.Length <= 2 || name.Length > 256) continue;
                var escaped = Regex.Escape(name);
                value = Regex.Replace(value, @"(?<![\p{L}\p{N}_])" + escaped + @"(?![\p{L}\p{N}_])", m =>
                {
                    if (HardwareLiteral(value, m)) return m.Value;
                    return identity[1];
                }, RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);
            }
            return value;
        }

        static readonly HashSet<string> HardwareVendors = new HashSet<string>(new[] { "Apple", "Intel", "AMD", "NVIDIA", "Microsoft", "Realtek", "Broadcom", "Qualcomm", "MediaTek",
                "ASUS", "ASUSTeK", "ASRock", "Dell", "Lenovo", "HP", "Gigabyte", "MSI", "Acer", "AuthenticAMD", "GenuineIntel" }, StringComparer.OrdinalIgnoreCase);

        static bool HardwareLiteral(string text, Match match)
        {
            if (!HardwareVendors.Contains(match.Value)) return false;
            int lower = Math.Max(0, match.Index - 160);
            int start = match.Index > 0 ? text.LastIndexOf('\n', match.Index - 1, match.Index - lower) : -1;
            start = Math.Max(lower, start + 1);
            string before = text.Substring(start, match.Index - start);
            int afterIndex = match.Index + match.Length;
            string after = text.Substring(afterIndex, Math.Min(96, text.Length - afterIndex));
            if (Regex.IsMatch(match.Value, @"(?i)\A(?:apple|nvidia|intel|microsoft|amd)\z") &&
                Regex.IsMatch(before, @"(?i)(?:^|[^a-z0-9_.-])com\.$") && after.StartsWith(".", StringComparison.Ordinal)) return true;
            if (string.Equals(match.Value, "NVIDIA", StringComparison.OrdinalIgnoreCase) &&
                (after.StartsWith("-macos-driver", StringComparison.OrdinalIgnoreCase) ||
                 (before.EndsWith("nullmoth-", StringComparison.OrdinalIgnoreCase) && Regex.IsMatch(after, @"^-[0-9]+\.[0-9]+\.[0-9]+\.tar\.gz")))) return true;
            if (Regex.IsMatch(before, @"(?i)(?:[""']?(?:manufacturer|vendor|board|motherboard|cpu|gpu|processor name)[""']?\s*[:=]\s*[""']?)$")) return true;
            // Only documented product/identifier prefixes receive the same treatment outside a typed field.
            return Regex.IsMatch(after, @"(?i)^\s*(?:\(R\)|\(0x[0-9a-f]+\)|GeForce\b|Quadro\b|RTX\b|GTX\b|Ryzen\b|Radeon\b|Core\b|UHD\b|Iris\b|HD Graphics\b|Wi-Fi\b|Wireless\b|Ethernet\b)");
        }
        static void RealParents(string directory)
        {
            for (var current = new DirectoryInfo(directory); current != null; current = current.Parent)
                if (current.Exists && (current.Attributes & FileAttributes.ReparsePoint) != 0)
                    throw new IOException("A diagnostic parent is a reparse point.");
        }
        internal static Outcome Save(string work, string kind, string version, string text)
        {
            string temporary = null;
            try
            {
                if (!Regex.IsMatch(kind ?? "", @"\A[a-z][a-z0-9-]{0,31}\z"))
                    throw new ArgumentException("Invalid diagnostic stage.");
                var directory = System.IO.Path.Combine(work, "diagnostic-reports");
                RealParents(directory);
                Directory.CreateDirectory(directory);
                RealParents(directory);
                string stem = DateTime.UtcNow.ToString("yyyyMMddTHHmmssfffZ") + "-" + kind + "-" + Guid.NewGuid().ToString("N");
                string path = System.IO.Path.Combine(directory, stem + ".txt");
                temporary = path + ".partial";
                var raw = text ?? "";
                bool truncated = raw.Length > MaxCharacters;
                var clean = Clean(truncated ? raw.Substring(0, MaxCharacters) : raw);
                if (truncated) clean += "\r\n[report truncated at local diagnostic limit]\r\n";
                var bytes = new UTF8Encoding(false).GetBytes("1401 " + Clean(version) + " local " + kind + " report\r\n" + clean);
                using (var file = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None, 4096, FileOptions.WriteThrough))
                {
                    file.Write(bytes, 0, bytes.Length);
                    file.Flush(true);
                }
                RealParents(directory);
                File.Move(temporary, path);
                temporary = null;
                return new Outcome { Path = path };
            }
            catch (Exception error)
            {
                return new Outcome { Failure = "The local diagnostic report could not be saved (" + error.GetType().Name + ", code " + error.HResult + "). Check free space and access to the app data folder, then retry. No saved report is claimed." };
            }
            finally
            {
                if (temporary != null) { try { File.Delete(temporary); } catch (IOException) { } catch (UnauthorizedAccessException) { } }
            }
        }
        internal static string[] Find(string work)
        {
            var directory = System.IO.Path.Combine(work, "diagnostic-reports");
            RealParents(directory);
            if (!Directory.Exists(directory)) return new string[0];
            return Directory.GetFiles(directory, "*.txt", SearchOption.TopDirectoryOnly)
                .Where(p => Regex.IsMatch(System.IO.Path.GetFileName(p), @"\A\d{8}T\d{9}Z-[a-z][a-z0-9-]{0,31}-[0-9a-f]{32}\.txt\z") &&
                            (File.GetAttributes(p) & FileAttributes.ReparsePoint) == 0)
                .OrderByDescending(p => System.IO.Path.GetFileName(p), StringComparer.Ordinal).Take(12).ToArray();
        }
        internal static bool IsLocal(string work, string path)
        {
            return string.Equals(System.IO.Path.GetDirectoryName(System.IO.Path.GetFullPath(path)),
                System.IO.Path.GetFullPath(System.IO.Path.Combine(work, "diagnostic-reports")), StringComparison.OrdinalIgnoreCase);
        }
    }
}
