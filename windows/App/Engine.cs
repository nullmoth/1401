using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Threading.Tasks;
using System.Security.Cryptography;
using System.Collections.Generic;
using System.Web.Script.Serialization;
using System.Text.RegularExpressions;

namespace A1401
{
    /// <summary>Runs the 1401 engine (portable Python + p1401, next to this exe) and streams its output.</summary>
    static class Engine
    {
        public static string Home { get { return AppDomain.CurrentDomain.BaseDirectory; } }
        public static string Python { get { return Path.Combine(Home, "engine", "python", "python.exe"); } }
        public static string AppDir { get { return Path.Combine(Home, "engine", "app"); } }
        // Never beside the exe: a OneDrive Desktop denies deleting there ("Access denied" on Check this PC)
        public static string Work { get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "NullMoth", "1401"); } }
        public static string NullMothDir { get { return Path.Combine(Home, "NullMoth"); } }

        public static string Missing()
        {
            if (!File.Exists(Python)) return Loc.T("The engine folder is missing next to 1401.exe (engine\\python\\python.exe). Copy the whole 1401 folder, not just the exe.");
            if (!Directory.Exists(Path.Combine(AppDir, "p1401"))) return Loc.T("The engine folder is incomplete (engine\\app\\p1401).");
            return null;
        }

        /// <summary>Runs python -m args in engine\app; every output line goes to onLine (on a worker thread).</summary>
        internal static DurableReport.Outcome LastReport;

        static string InputFingerprints()
        {
            var text = new StringBuilder("fingerprint scope: files observed before this attempt; not executed-memory identity\r\n");
            foreach (var item in new[] {
                new[] { "app", Path.Combine(Home, "1401.exe") },
                new[] { "build-manifest", Path.Combine(Home, "BUILD-MANIFEST.json") },
                new[] { "engine-source", Path.Combine(AppDir, "p1401", "engine.py") },
                new[] { "upstream-pin", Path.Combine(AppDir, "upstream", "PINNED.json") },
                new[] { "iasl", Path.Combine(AppDir, "upstream", "OpCore-Simplify", "Scripts", "iasl.exe") }
            })
            {
                try
                {
                    var info = new FileInfo(item[1]);
                    if (!info.Exists || info.Length > 32 * 1024 * 1024 || (info.Attributes & FileAttributes.ReparsePoint) != 0)
                    { text.AppendLine(item[0] + ": unavailable"); continue; }
                    using (var file = new FileStream(item[1], FileMode.Open, FileAccess.Read, FileShare.Read))
                    using (var hash = SHA256.Create())
                        text.AppendLine(item[0] + ": SHA256 " + BitConverter.ToString(hash.ComputeHash(file)).Replace("-", "").ToLowerInvariant());
                }
                catch (Exception error) { text.AppendLine(item[0] + ": unavailable (" + error.GetType().Name + ", code " + error.HResult + ")"); }
            }
            try
            {
                var manifest = Path.Combine(Home, "BUILD-MANIFEST.json");
                if (File.Exists(manifest) && new FileInfo(manifest).Length <= 2 * 1024 * 1024)
                {
                    var value = new JavaScriptSerializer { MaxJsonLength = 2 * 1024 * 1024 }.Deserialize<Dictionary<string, object>>(File.ReadAllText(manifest));
                    object source;
                    if (value.TryGetValue("source_commit", out source) && Regex.IsMatch("" + source, @"\A[0-9a-f]{40}\z"))
                        text.AppendLine("manifest declared source commit: " + source);
                    object fileMap;
                    if (value.TryGetValue("files", out fileMap) && fileMap is Dictionary<string, object>)
                        foreach (var item in (Dictionary<string, object>)fileMap)
                            if (Regex.IsMatch(item.Key, @"\ANullMoth/(nullmoth-nvidia-\d+\.\d+\.\d+\.tar\.gz|1401-Mac-\d+\.\d+\.\d+\.zip)\z") &&
                                Regex.IsMatch("" + item.Value, @"\A[0-9a-f]{64}\z"))
                                text.AppendLine("manifest declared companion pin " + Path.GetFileName(item.Key) + ": " + item.Value);
                }
            }
            catch (Exception error) { text.AppendLine("manifest pins unavailable (" + error.GetType().Name + ", code " + error.HResult + ")"); }
            return text.ToString();
        }

        public static Task<int> Run(string args, Action<string> onLine)
        {
            return Task.Run(() =>
            {
                LastReport = null;
                string attempt = Guid.NewGuid().ToString("N");
                string stage = args.StartsWith("p1401.scan ", StringComparison.Ordinal) ? "scan" :
                    args.StartsWith("p1401 build ", StringComparison.Ordinal) ? "build" :
                    args.StartsWith("p1401.usbwriter ", StringComparison.Ordinal) ? "write" : "operation";
                string context = "app-reported distribution version: " + System.Windows.Forms.Application.ProductVersion + "\r\nengine identity: engine-source SHA256 observation below; no separate engine version is declared\r\nattempt: " + attempt + "\r\nstage: " + stage + "\r\noperation: " + args + "\r\n";
                var started = DurableReport.Save(Work, stage + "-start", System.Windows.Forms.Application.ProductVersion,
                    context + "state: attempt recorded before execution\r\n");
                if (!started.Saved)
                {
                    LastReport = started;
                    onLine(started.Failure + " The operation was not started.");
                    return 1;
                }
                var output = new StringBuilder();
                var sync = new object();
                bool truncated = false;
                Action<string> record = line =>
                {
                    lock (sync)
                    {
                        int left = DurableReport.MaxCharacters - output.Length;
                        if (left > 0) output.AppendLine(line.Length > left ? line.Substring(0, left) : line);
                        if (line.Length > left) truncated = true;
                    }
                    try { onLine(line); }
                    catch (Exception notification)
                    {
                        lock (sync)
                            if (output.Length < DurableReport.MaxCharacters - 256)
                                output.AppendLine("Output notification failed (" + notification.GetType().Name + ", code " + notification.HResult + "); local reporting continues.");
                    }
                };
                int exit = 1;
                try
                {
                    context += InputFingerprints();
                    var psi = new ProcessStartInfo(Python, "-u -m " + args)
                    {
                        WorkingDirectory = AppDir, UseShellExecute = false, CreateNoWindow = true,
                        RedirectStandardOutput = true, RedirectStandardError = true,
                        StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8
                    };
                    psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
                    psi.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1";
                    using (var p = new Process { StartInfo = psi })
                    {
                        p.OutputDataReceived += (s, e) => { if (e.Data != null) record(e.Data); };
                        p.ErrorDataReceived += (s, e) => { if (e.Data != null) record(e.Data); };
                        p.Start(); p.BeginOutputReadLine(); p.BeginErrorReadLine();
                        p.WaitForExit();
                        exit = p.ExitCode;
                    }
                }
                catch (Exception error)
                {
                    record("Engine operation failed (" + error.GetType().Name + ", code " + error.HResult + "). Check the complete extracted app folder and send the saved local report.");
                    var cause = error.InnerException;
                    for (int depth = 0; cause != null && depth < 4; depth++, cause = cause.InnerException)
                        record("Engine exception cause (" + cause.GetType().Name + ", code " + cause.HResult + ").");
                }
                finally
                {
                    string saved;
                    lock (sync) saved = context + "exit code: " + exit + "\r\n" + output + (truncated ? "\r\n[output truncated]" : "");
                    LastReport = DurableReport.Save(Work, stage + "-final", System.Windows.Forms.Application.ProductVersion, saved);
                }
                return exit;
            });
        }

        public static string Q(string s) { return "\"" + s.Replace("\"", "\\\"") + "\""; }
    }
}
