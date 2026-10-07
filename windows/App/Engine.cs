using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Threading.Tasks;

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
            if (!File.Exists(Python)) return "The engine folder is missing next to 1401.exe (engine\\python\\python.exe). Copy the whole 1401 folder, not just the exe.";
            if (!Directory.Exists(Path.Combine(AppDir, "p1401"))) return "The engine folder is incomplete (engine\\app\\p1401).";
            return null;
        }

        /// <summary>Runs python -m args in engine\app; every output line goes to onLine (on a worker thread).</summary>
        public static Task<int> Run(string args, Action<string> onLine)
        {
            return Task.Run(() =>
            {
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
                    p.OutputDataReceived += (s, e) => { if (e.Data != null) onLine(e.Data); };
                    p.ErrorDataReceived += (s, e) => { if (e.Data != null) onLine(e.Data); };
                    p.Start(); p.BeginOutputReadLine(); p.BeginErrorReadLine();
                    p.WaitForExit();
                    return p.ExitCode;
                }
            });
        }

        public static string Q(string s) { return "\"" + s.Replace("\"", "\\\"") + "\""; }
    }
}
