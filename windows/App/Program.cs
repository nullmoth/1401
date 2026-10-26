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
            // The window drawn to PNG files, dark and light, for review without a Windows PC (CI uploads them).
            if (args.Length == 2 && args[0] == "--screenshot")
            {
                System.IO.Directory.CreateDirectory(args[1]);
                foreach (var light in new[] { false, true })
                {
                    Glass.Force(light);
                    using (var f = new MainForm(true) { StartPosition = FormStartPosition.Manual, Location = new System.Drawing.Point(0, 0) })
                    {
                        f.Show(); Application.DoEvents();
                        using (var bmp = new System.Drawing.Bitmap(f.Width, f.Height))
                        {
                            f.DrawToBitmap(bmp, new System.Drawing.Rectangle(0, 0, f.Width, f.Height));
                            bmp.Save(System.IO.Path.Combine(args[1], light ? "1401-light.png" : "1401-dark.png"), System.Drawing.Imaging.ImageFormat.Png);
                        }
                        f.Close();
                    }
                }
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
