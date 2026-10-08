using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Threading.Tasks;
using A1401;
class ReportReliability
{
    static int checks;
    static string stage = "synthetic_identity";
    static void Require(bool value) { checks++; if (!value) throw new Exception("Diagnostic fixture assertion " + checks); }
    static int Main(string[] args)
    {
        try { return RunFixtures(args); }
        catch (Exception error)
        {
            Console.WriteLine("{\"ok\":false,\"assertion_number\":" + checks + ",\"stage\":\"" + stage + "\",\"error_type\":\"" + error.GetType().Name + "\",\"error_code\":" + error.HResult + "}");
            return 1;
        }
    }
    static int RunFixtures(string[] args)
    {
        if (args.Length > 0)
        {
            Console.WriteLine("malformed build result fixture");
            Console.Error.WriteLine("bounded stderr fixture");
            return 13;
        }
        string directory = Path.Combine(Path.GetTempPath(), "report-fixture-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        try
        {
            Require(DurableReport.CleanIdentity(@"C:\Users\UnitAccount\Logs\x.txt", "UnitAccount", "UnitHost", @"C:\Users\UnitAccount") == @"%USERPROFILE%\Logs\x.txt");
            Require(DurableReport.CleanIdentity(@"C:\\Users\\UnitAccount\\Logs", "UnitAccount", "UnitHost", @"C:\Users\UnitAccount") == @"%USERPROFILE%\\Logs");
            Require(DurableReport.CleanIdentity("User: APPLE\ncom.apple.driver.AppleIntelFramebuffer\nAppleIntelGraphics", "apple", "UnitHost", "") == "User: user\ncom.apple.driver.AppleIntelFramebuffer\nAppleIntelGraphics");
            Require(DurableReport.CleanIdentity("Manufacturer: NVIDIA\nGPU: NVIDIA GeForce RTX 4060\nuser NVIDIA\nhost NVIDIA", "NVIDIA", "NVIDIA", "") == "Manufacturer: NVIDIA\nGPU: NVIDIA GeForce RTX 4060\nuser user\nhost this-pc");
            Require(DurableReport.CleanIdentity("\"Manufacturer\": \"NVIDIA\"\n\"username\": \"NVIDIA\"", "NVIDIA", "UnitHost", "") == "\"Manufacturer\": \"NVIDIA\"\n\"username\": \"user\"");
            // An unknown namespace containing the account name is private; OS property names stay intact.
            Require(DurableReport.CleanIdentity("macOS machdep.cpu com.mac.driver user MAC", "mac", "UnitHost", "") == "macOS machdep.cpu com.user.driver user user");
            Require(DurableReport.CleanIdentity("Vendor: Intel\nIntel(R) Core(TM) CPU\nAccount=INTEL\nerror Intel", "intel", "UnitHost", "") == "Vendor: Intel\nIntel(R) Core(TM) CPU\nAccount=user\nerror user");
            Require(DurableReport.CleanIdentity(@"\\UnitHost\share https://UNITHOST/path Hostname=UnitHost", "UnitAccount", "UnitHost", "") == @"\\this-pc\share https://this-pc/path Hostname=this-pc");
            Require(DurableReport.CleanIdentity("Username: ab\nHost: xy\nPCI 10DE-28E0 subsystem 17AA-3CF2", "ab", "xy", "") == "Username: user\nHost: this-pc\nPCI 10DE-28E0 subsystem 17AA-3CF2");
            Require(DurableReport.CleanIdentity("com.UnitAccount.app UnitHost-logs https://UnitHost.local/path", "UnitAccount", "UnitHost", "") == "com.user.app this-pc-logs https://this-pc.local/path");
            Require(DurableReport.CleanIdentity("com.nvidia.driver nullmoth-nvidia-1.0.11.tar.gz nvidia-macos-driver User=NVIDIA", "NVIDIA", "UnitHost", "") == "com.nvidia.driver nullmoth-nvidia-1.0.11.tar.gz nvidia-macos-driver User=user");
            Require(DurableReport.CleanIdentity(null, null, null, null) == "");
            Require(DurableReport.CleanIdentity("User: UnitAccount\nHOST=UnitHost\nunitaccount\nUNITHOST", "UnitAccount", "UnitHost", "") == "User: user\nHOST=this-pc\nuser\nthis-pc");
            stage = "local_report_filesystem";
            var work = Path.Combine(directory, "missing", "app-data");
            var one = DurableReport.Save(work, "build", "1.0.23", "download failed\r\nretained output");
            Require(one.Saved && File.ReadAllText(one.Path).Contains("download failed"));
            var bytes = File.ReadAllBytes(one.Path);
            Require(DurableReport.Find(work).Contains(one.Path));
            // Reopening after a simulated network outage does not move, delete or rewrite the report.
            Require(File.ReadAllBytes(DurableReport.Find(work).Single()).SequenceEqual(bytes));
            var outputs = Enumerable.Range(0, 8).Select(i => Task.Run(() => DurableReport.Save(work, "scan", "1.0.23", "scan " + i))).ToArray();
            Task.WaitAll(outputs);
            Require(outputs.All(t => t.Result.Saved));
            Require(outputs.Select(t => t.Result.Path).Distinct().Count() == 8);
            Require(File.ReadAllBytes(one.Path).SequenceEqual(bytes));
            var bounded = DurableReport.Save(work, "write", "1.0.23", new string('x', 1000000));
            Require(bounded.Saved && new FileInfo(bounded.Path).Length < 2 * 1024 * 1024);
            Require(File.ReadAllText(bounded.Path).Contains("report truncated"));
            Require(!Directory.GetFiles(Path.Combine(work, "diagnostic-reports"), "*.partial").Any());
            var blocker = Path.Combine(directory, "blocked"); File.WriteAllText(blocker, "foreign bytes");
            var failed = DurableReport.Save(blocker, "scan", "1.0.23", "output");
            Require(!failed.Saved && failed.Failure.Contains("No saved report is claimed"));
            Require(File.ReadAllText(blocker) == "foreign bytes");
            var again = Path.Combine(directory, "recreated"); Directory.CreateDirectory(again); Directory.Delete(again);
            Require(DurableReport.Save(again, "scan", "1.0.23", "new scan").Saved);
            Require(DurableReport.IsLocal(work, one.Path));
            Require(!DurableReport.IsLocal(work, Path.Combine(directory, "outside.txt")));
            // The executable is isolated from portable Python: production launch fails and still publishes a report.
            stage = "engine_missing_launch";
            var seen = new List<string>(); int rc = Engine.Run("p1401 build missing missing missing --json", l => { lock (seen) seen.Add(l); }).GetAwaiter().GetResult();
            Require(rc != 0 && Engine.LastReport != null && Engine.LastReport.Saved);
            Require(File.ReadAllText(Engine.LastReport.Path).Contains("Engine operation failed"));
            stage = "engine_child_output";
            var firstFinal = Engine.LastReport.Path;
            var engineDirectory = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "engine");
            Directory.CreateDirectory(Path.Combine(engineDirectory, "python"));
            Directory.CreateDirectory(Path.Combine(engineDirectory, "app"));
            File.Copy(System.Reflection.Assembly.GetExecutingAssembly().Location, Path.Combine(engineDirectory, "python", "python.exe"));
            rc = Engine.Run("p1401 build missing missing missing --json", l => { lock (seen) seen.Add(l); }).GetAwaiter().GetResult();
            Require(rc == 13 && Engine.LastReport.Saved);
            var final = File.ReadAllText(Engine.LastReport.Path);
            Require(final.Contains("bounded stderr fixture") && final.Contains("malformed build result fixture"));
            Require(final.Contains("exit code: 13") && final.Contains("stage: build") && final.Contains("attempt:"));
            Require(final.Contains("engine-source: unavailable"));
            var attempt = System.Text.RegularExpressions.Regex.Match(final, @"attempt: ([0-9a-f]{32})").Groups[1].Value;
            Require(attempt.Length == 32);
            Require(DurableReport.Find(Engine.Work).Any(p => File.ReadAllText(p).Contains(attempt) && File.ReadAllText(p).Contains("attempt recorded before execution")));
            Require(File.Exists(firstFinal));
            File.Delete(firstFinal); File.Delete(Engine.LastReport.Path);
            Console.WriteLine("{\"ok\":true,\"assertions\":" + checks + "}"); return 0;
        }
        finally {
            var previous = stage; stage = "fixture_cleanup";
            Directory.Delete(directory, true); stage = previous;
        }
    }
}
