using System;
using System.Collections.Generic;
using System.IO;
using System.Web.Script.Serialization;
using System.Text.RegularExpressions;

namespace A1401
{
    /// <summary>Read only the bounded receipt for an explicit scan run; saved evidence is never a current-PC claim.</summary>
    static class ScanEvidence
    {
        internal const int MaxBytes = 2 * 1024 * 1024;
        static readonly Regex RunToken = new Regex(@"^[0-9a-f]{32}$");
        internal sealed class Selection
        {
            internal string Path;
            internal bool CurrentRun;
        }
        internal static string RunDirectory(string work, string token)
        {
            if (token == null || !RunToken.IsMatch(token)) throw new ArgumentException("Invalid scan run token.");
            return System.IO.Path.Combine(work, "scan-" + token);
        }
        internal static void Remember(string work, string token)
        {
            RunDirectory(work, token);
            Directory.CreateDirectory(work);
            var destination = System.IO.Path.Combine(work, "latest-scan.json");
            var temporary = destination + ".tmp-" + Guid.NewGuid().ToString("N");
            File.WriteAllText(temporary, new JavaScriptSerializer().Serialize(new Dictionary<string, object> {
                { "schema", "nullmoth-latest-scan/1" }, { "run_id", token } }));
            if (File.Exists(destination)) File.Replace(temporary, destination, null);
            else File.Move(temporary, destination);
        }
        static Dictionary<string, object> Read(string path, int maximum)
        {
            try
            {
                if ((File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0 || new FileInfo(path).Length > maximum) return null;
                return new JavaScriptSerializer { MaxJsonLength = maximum }.Deserialize<Dictionary<string, object>>(File.ReadAllText(path));
            }
            catch (Exception) { return null; }
        }
        internal static Selection Find(string work, string currentToken, bool allowSaved)
        {
            string token = currentToken;
            bool current = token != null;
            if (!current)
            {
                if (!allowSaved) return null;
                var latest = Read(System.IO.Path.Combine(work, "latest-scan.json"), 4096);
                if (latest == null || !latest.ContainsKey("schema") || "" + latest["schema"] != "nullmoth-latest-scan/1" || !latest.ContainsKey("run_id")) return null;
                token = "" + latest["run_id"];
            }
            if (token == null || !RunToken.IsMatch(token)) return null;
            var dir = RunDirectory(work, token);
            try { if ((File.GetAttributes(dir) & FileAttributes.ReparsePoint) != 0) return null; }
            catch (Exception) { return null; }
            var path = System.IO.Path.Combine(dir, "scan-evidence.json");
            var receipt = Read(path, MaxBytes);
            if (receipt == null || !receipt.ContainsKey("schema") || "" + receipt["schema"] != "nullmoth-scan-evidence/1" ||
                !receipt.ContainsKey("run_id") || "" + receipt["run_id"] != token) return null;
            return new Selection { Path = path, CurrentRun = current };
        }
        internal static bool Verify()
        {
            var work = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "1401-scan-test-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(work);
            try
            {
                var token = Guid.NewGuid().ToString("N");
                var dir = RunDirectory(work, token); Directory.CreateDirectory(dir);
                var path = System.IO.Path.Combine(dir, "scan-evidence.json");
                File.WriteAllText(path, new JavaScriptSerializer().Serialize(new Dictionary<string, object> {
                    { "schema", "nullmoth-scan-evidence/1" }, { "run_id", token }, { "scan_status", "failed" }, { "report_sha256", null } }));
                Remember(work, token);
                var current = Find(work, token, false);
                var saved = Find(work, null, true);
                if (current == null || !current.CurrentRun || saved == null || saved.CurrentRun || current.Path != saved.Path) return false;
                if (Find(work, Guid.NewGuid().ToString("N"), true) != null) return false; // Never substitute a stale run.
                File.WriteAllText(path, "{\"schema\":\"nullmoth-scan-evidence/1\",\"run_id\":\"other\"}");
                if (Find(work, token, false) != null) return false;
                File.WriteAllText(path, new string('x', MaxBytes + 1));
                return Find(work, token, false) == null;
            }
            finally { Directory.Delete(work, true); }
        }
    }
}
