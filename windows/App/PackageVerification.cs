using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Linq;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace A1401
{
    /// <summary>Non-destructive packaged startup check for the Windows build job.</summary>
    static class PackageVerification
    {
        static bool VerifyLocalReports()
        {
            var root = Path.Combine(Path.GetTempPath(), "1401-report-verification-" + Guid.NewGuid().ToString("N"));
            try
            {
                var saved = DurableReport.Save(root, "verify", Application.ProductVersion, "preserved operation failure output");
                if (!saved.Saved) return false;
                var bytes = File.ReadAllBytes(saved.Path);
                if (!DurableReport.Find(root).Contains(saved.Path)) return false;
                var second = DurableReport.Save(root, "verify", Application.ProductVersion, "second attempt output");
                if (!second.Saved || second.Path == saved.Path || !File.ReadAllBytes(saved.Path).SequenceEqual(bytes)) return false;
                var foreign = Path.Combine(root, "foreign-file");
                File.WriteAllText(foreign, "retained foreign bytes");
                var failure = DurableReport.Save(foreign, "verify", Application.ProductVersion, "must not overwrite");
                return !failure.Saved && !string.IsNullOrEmpty(failure.Failure) && File.ReadAllText(foreign) == "retained foreign bytes" &&
                    File.ReadAllBytes(saved.Path).SequenceEqual(bytes);
            }
            finally { if (Directory.Exists(root)) Directory.Delete(root, true); }
        }

        public static int Run(string resultPath)
        {
            var result = new Dictionary<string, object>();
            bool shown = false;
            try
            {
                result["assembly_version"] = Assembly.GetExecutingAssembly().GetName().Version.ToString(3);
                result["product_version"] = Application.ProductVersion;
                result["engine_complete"] = Engine.Missing() == null;
                var batches = new HashSet<string>();
                bool freshBatches = true;
                for (int i = 0; i < 1024; i++)
                {
                    var batch = MainForm.NewBatch();
                    freshBatches &= System.Text.RegularExpressions.Regex.IsMatch(batch, @"^1401-app-[0-9a-f]{16}$") && batches.Add(batch);
                }
                result["fresh_upload_batches"] = freshBatches;
                result["scan_evidence_binding"] = ScanEvidence.Verify();
                result["packaged_local_report_lifecycle"] = VerifyLocalReports();
                result["support_notices_visible"] = MainForm.IsSupportNotice("Laptop display note: unsupported panel") &&
                                                    MainForm.IsSupportNotice("Intel I225-LM vP requires link testing") &&
                                                    MainForm.IsSupportNotice("NullMoth driver selected") &&
                                                    !MainForm.IsSupportNotice("ACPI loader transcript");
                using (var form = new MainForm(true))
                using (var timer = new Timer { Interval = 250 })
                {
                    form.Shown += (sender, args) => timer.Start();
                    timer.Tick += (sender, args) =>
                    {
                        timer.Stop();
                        shown = form.Visible && form.IsHandleCreated && form.Controls.Count > 0;
                        result["support_notices_visible"] = (bool)result["support_notices_visible"] && form.VerifySupportNoticePresentation();
                        result["firmware_prerequisite_navigation"] = form.VerifyFirmwarePrerequisiteNavigation();
                        result["firmware_navigation_fixture_phase"] = form.FirmwareVerificationPhase;
                        form.Close();
                    };
                    Application.Run(form);
                    form.Dispose();
                    form.OfferStickLogs(true);
                    result["closed_form_log_collection_guard"] = form.IsDisposed;
                }
                result["window_shown_and_closed"] = shown;
                result["ok"] = shown && (bool)result["engine_complete"] && (bool)result["closed_form_log_collection_guard"] &&
                               (bool)result["support_notices_visible"] && (bool)result["fresh_upload_batches"] && (bool)result["scan_evidence_binding"] &&
                               (bool)result["firmware_prerequisite_navigation"] && (bool)result["packaged_local_report_lifecycle"];
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
