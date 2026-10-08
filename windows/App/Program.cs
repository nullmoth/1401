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
            // any crash of 1401 itself leaves crash-log.txt; the next start offers to send it with the other logs
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);
            Application.ThreadException += (s, e) => { CrashLog(e.Exception); MessageBox.Show(e.Exception.Message + "\r\n\r\nA crash log was saved; 1401 offers to send it the next time it starts.", "1401", MessageBoxButtons.OK, MessageBoxIcon.Error); };
            AppDomain.CurrentDomain.UnhandledException += (s, e) => CrashLog(e.ExceptionObject as Exception);
            Application.Run(new MainForm());
        }

        static void CrashLog(Exception ex)
        {
            try
            {
                var dir = System.IO.Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "NullMoth", "1401");
                System.IO.Directory.CreateDirectory(dir);
                var text = "1401 " + Application.ProductVersion + " crash " + DateTime.UtcNow.ToString("u") + "\r\n" + Environment.OSVersion + "\r\n\r\n" + ex;
                var user = Environment.UserName; if (!string.IsNullOrEmpty(user) && user.Length > 2) text = text.Replace(user, "user");
                System.IO.File.AppendAllText(System.IO.Path.Combine(dir, "crash-log.txt"), text + "\r\n\r\n");
            }
            catch (Exception) { }
        }
    }
}
