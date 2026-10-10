using System;
using System.Windows.Forms;

namespace A1401
{
    static class Program
    {
        [STAThread]
        static void Main(string[] args)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            if (args.Length == 2 && args[0] == "--verify-package")
            {
                Application.SetUnhandledExceptionMode(UnhandledExceptionMode.ThrowException);
                Environment.ExitCode = PackageVerification.Run(args[1]);
                return;
            }
            // A saved local crash report is offered after restart; saving failures are reported explicitly.
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);
            Application.ThreadException += (s, e) => { var report = CrashLog(e.Exception); MessageBox.Show(DurableReport.Clean(e.Exception.Message) + "\r\n\r\n" + (report.Saved ? Loc.T("A local crash report was saved at ") + report.Path + Loc.T(". Scan for logs and send them can retry after restart.") : report.Failure), "1401", MessageBoxButtons.OK, MessageBoxIcon.Error); };
            AppDomain.CurrentDomain.UnhandledException += (s, e) => CrashLog(e.ExceptionObject as Exception);
            Application.Run(new MainForm());
        }

        static DurableReport.Outcome CrashLog(Exception ex)
        {
            return DurableReport.Save(Engine.Work, "crash", Application.ProductVersion,
                "time: " + DateTime.UtcNow.ToString("u") + "\r\n" + Environment.OSVersion + "\r\n\r\n" + ex);
        }
    }
}
