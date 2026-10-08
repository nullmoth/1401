using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace A1401
{
    /// <summary>Non-destructive packaged startup check for the Windows build job.</summary>
    static class PackageVerification
    {
        public static int Run(string resultPath)
        {
            var result = new Dictionary<string, object>();
            bool shown = false;
            try
            {
                result["assembly_version"] = Assembly.GetExecutingAssembly().GetName().Version.ToString(3);
                result["product_version"] = Application.ProductVersion;
                result["engine_complete"] = Engine.Missing() == null;
                using (var form = new MainForm(true))
                using (var timer = new Timer { Interval = 250 })
                {
                    form.Shown += (sender, args) => timer.Start();
                    timer.Tick += (sender, args) =>
                    {
                        timer.Stop();
                        shown = form.Visible && form.IsHandleCreated && form.Controls.Count > 0;
                        form.Close();
                    };
                    Application.Run(form);
                }
                result["window_shown_and_closed"] = shown;
                result["ok"] = shown && (bool)result["engine_complete"];
            }
            catch (Exception error)
            {
                result["ok"] = false;
                result["error_type"] = error.GetType().FullName;
            }
            File.WriteAllText(resultPath, new JavaScriptSerializer().Serialize(result));
            return (bool)result["ok"] ? 0 : 1;
        }
    }
}
