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
            value = value ?? "";
            string home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
            if (!string.IsNullOrEmpty(home) && home.Length > 3)
                value = Regex.Replace(value, Regex.Escape(home), "%USERPROFILE%", RegexOptions.IgnoreCase);
            foreach (var item in new[] { new[] { Environment.UserName, "user" }, new[] { Environment.MachineName, "this-pc" } })
                if (!string.IsNullOrEmpty(item[0]) && item[0].Length > 2)
                    value = Regex.Replace(value, @"(?<![\p{L}\p{N}_])" + Regex.Escape(item[0]) + @"(?![\p{L}\p{N}_])", item[1], RegexOptions.IgnoreCase);
            return value;
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
