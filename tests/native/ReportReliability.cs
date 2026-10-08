using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Threading.Tasks;
using A1401;
class ReportReliability
{
    static int checks;
    static void Require(bool value) { checks++; if (!value) throw new Exception("Diagnostic fixture assertion " + checks); }
    static int Main(string[] args)
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
            var seen = new List<string>(); int rc = Engine.Run("p1401 build missing missing missing --json", l => { lock (seen) seen.Add(l); }).GetAwaiter().GetResult();
            Require(rc != 0 && Engine.LastReport != null && Engine.LastReport.Saved);
            Require(File.ReadAllText(Engine.LastReport.Path).Contains("Engine operation failed"));
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
        finally { Directory.Delete(directory, true); }
    }
}
