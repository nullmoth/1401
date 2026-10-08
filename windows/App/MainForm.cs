using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace A1401
{
    class MainForm : Form
    {
        static readonly string[] Steps = { "Introduction", "Check this PC", "Build the Mac setup", "Your BIOS steps", "Create the macOS stick", "Done" };
        int page;
        readonly Label[] side = new Label[Steps.Length];
        readonly Panel body = new Panel();
        readonly Label title = new Label(), note = new Label();
        readonly Button back = new Button(), next = new Button();
        readonly TextBox log = new TextBox();
        readonly ProgressBar bar = new ProgressBar();
        readonly ComboBox disks = new ComboBox();
        readonly Button refresh = new Button();
        readonly WebBrowser guide = new WebBrowser();
        readonly LinkLabel ocLink = new LinkLabel();
        readonly LinkLabel logLink = new LinkLabel();
        readonly LinkLabel drvLink = new LinkLabel();
        readonly LinkLabel firmwareLink = new LinkLabel();
        readonly ListView facts = new ListView();
        bool busy, scanned, built, written, listing, showingPrerequisites;
        int prerequisiteReturnPage = 1;
        string firmwareGuideFile;
        string scanDir, scanRunId, efiDir, guideFile, darwin = "24", macosFull = "24.99.99", summary = "";

        public MainForm(bool verificationMode = false)
        {
            // Every bound below is in 96-DPI pixels. On a 150-200 % display (most 4K screens and many laptops) the
            // point-sized fonts grew with the display while the boxes kept their 96-DPI size, so text was cut off.
            // Scale the whole layout with the display, as the Windows Forms designer does for its own forms.
            SuspendLayout();
            AutoScaleDimensions = new SizeF(96F, 96F); AutoScaleMode = AutoScaleMode.Dpi;
            Text = "1401 Assistant";
            Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
            ClientSize = new Size(900, 620);
            FormBorderStyle = FormBorderStyle.FixedSingle; MaximizeBox = false;
            BackColor = Theme.Bg; ForeColor = Theme.Text; Font = Theme.Body;
            StartPosition = FormStartPosition.CenterScreen;
            if (!verificationMode) Shown += (o, e) => OfferStickLogs(false);

            var head = new Panel { Dock = DockStyle.Top, Height = 74, BackColor = Theme.Panel };
            var mark = new PictureBox { Image = Theme.Mark(), SizeMode = PictureBoxSizeMode.Zoom, Bounds = new Rectangle(14, 9, 56, 56) };
            var brand = new Label { Text = "NullMoth", Font = Theme.Brand, ForeColor = Theme.Purple, AutoSize = true, Location = new Point(80, 8) };
            var sub = new Label { Text = "1401 Assistant  -  macOS on the PC you already own", Font = Theme.Mono, ForeColor = Theme.Cyan, AutoSize = true, Location = new Point(84, 46) };
            head.Controls.AddRange(new Control[] { mark, brand, sub });

            var nav = new Panel { Dock = DockStyle.Left, Width = 220, BackColor = Theme.Panel2, Padding = new Padding(12, 16, 8, 8) };
            for (int i = Steps.Length - 1; i >= 0; i--)
            {
                side[i] = new Label { Text = (i + 1) + ".  " + Steps[i], Dock = DockStyle.Top, Height = 34, Font = Theme.Body, ForeColor = Theme.Muted };
                nav.Controls.Add(side[i]);
            }

            var foot = new Panel { Dock = DockStyle.Bottom, Height = 56, BackColor = Theme.Panel };
            back.Text = "< Back"; back.Bounds = new Rectangle(560, 12, 150, 32); Theme.Style(back, false);
            next.Text = "Continue >"; next.Bounds = new Rectangle(720, 12, 160, 32); Theme.Style(next);
            back.Click += (s, e) => {
                if (page == 3 && showingPrerequisites) { showingPrerequisites = false; Go(prerequisiteReturnPage); }
                else Go(page - 1);
            }; next.Click += (s, e) => OnNext();
            foot.Controls.AddRange(new Control[] { back, next });

            body.Dock = DockStyle.Fill; body.Padding = new Padding(24, 18, 24, 12); body.BackColor = Theme.Bg;
            title.Font = Theme.Title; title.ForeColor = Theme.Text; title.AutoSize = false; title.Bounds = new Rectangle(24, 14, 620, 40);
            note.AutoSize = false; note.Bounds = new Rectangle(24, 58, 620, 96); note.ForeColor = Theme.Text;
            log.Multiline = true; log.ReadOnly = true; log.ScrollBars = ScrollBars.Vertical; log.BackColor = Color.Black;
            log.ForeColor = Theme.Cyan; log.Font = new Font("Courier New", 9f); log.BorderStyle = BorderStyle.FixedSingle;
            log.Bounds = new Rectangle(24, 330, 620, 140);
            bar.Bounds = new Rectangle(24, 300, 620, 18);
            facts.View = View.Details; facts.FullRowSelect = true; facts.HeaderStyle = ColumnHeaderStyle.Nonclickable;
            facts.BackColor = Theme.Panel; facts.ForeColor = Theme.Text; facts.Font = new Font("Courier New", 9.5f);
            facts.Columns.Add("", 170); facts.Columns.Add("", 440); facts.Bounds = new Rectangle(24, 156, 620, 136);
            disks.DropDownStyle = ComboBoxStyle.DropDownList; disks.Bounds = new Rectangle(24, 170, 500, 28);
            disks.BackColor = Theme.Panel; disks.ForeColor = Theme.Text; disks.Font = new Font("Courier New", 10f);
            refresh.Text = "Refresh"; refresh.Bounds = new Rectangle(534, 168, 110, 30); Theme.Style(refresh, false);
            refresh.Click += (s, e) => FillDisks();
            guide.Bounds = new Rectangle(24, 110, 620, 360); guide.ScriptErrorsSuppressed = true;
            ocLink.Text = "OpenCore Install Guide (dortania.github.io/OpenCore-Install-Guide)"; ocLink.AutoSize = true;
            ocLink.Location = new Point(24, 300); ocLink.LinkColor = Theme.Cyan; ocLink.Font = new Font("Verdana", 9.5f);
            ocLink.LinkClicked += (s, e) => System.Diagnostics.Process.Start("https://dortania.github.io/OpenCore-Install-Guide/");
            logLink.Text = "Something went wrong? Scan for logs and send them"; logLink.AutoSize = true;
            logLink.Location = new Point(24, 330); logLink.LinkColor = Theme.Cyan; logLink.Font = new Font("Verdana", 9.5f);
            logLink.LinkClicked += (s, e) => OfferStickLogs(true);
            drvLink.Text = "Update the NVIDIA driver (newest release, here and on your 1401 stick)"; drvLink.AutoSize = true;
            drvLink.Location = new Point(24, 355); drvLink.LinkColor = Theme.Cyan; drvLink.Font = new Font("Verdana", 9.5f);
            drvLink.LinkClicked += (s, e) => UpdateDriver();
            firmwareLink.Text = "Review firmware prerequisites"; firmwareLink.AutoSize = true;
            firmwareLink.Location = new Point(24, 300); firmwareLink.LinkColor = Theme.Cyan; firmwareLink.Font = new Font("Verdana", 9.5f);
            firmwareLink.LinkClicked += (s, e) => {
                if (busy || firmwareGuideFile == null || !File.Exists(firmwareGuideFile)) return;
                prerequisiteReturnPage = page; showingPrerequisites = true; Go(3);
            };
            body.Controls.AddRange(new Control[] { title, note, facts, bar, log, disks, refresh, guide, ocLink, logLink, drvLink, firmwareLink });

            Controls.Add(body); Controls.Add(nav); Controls.Add(foot); Controls.Add(head);
            ResumeLayout(false); PerformLayout();
            // List view columns are not part of autoscaling.
            float k = CurrentAutoScaleDimensions.Width / 96F;
            if (k > 1.01F) foreach (ColumnHeader c in facts.Columns) c.Width = (int)(c.Width * k);
            Go(0);
        }

        // "Update driver": the newest driver release and 1401 Mac app, verified against the release's SHA256SUMS.txt, into
        // this app's NullMoth folder (what the next stick gets) and onto any plugged-in 1401 stick (what the Mac installs).
        async void UpdateDriver()
        {
            if (busy) return;
            busy = true; drvLink.Enabled = false;
            var dirs = new List<string> { Engine.NullMothDir };
            foreach (var drv in System.IO.DriveInfo.GetDrives())
            {
                try { if (drv.IsReady && drv.DriveType == System.IO.DriveType.Removable && Directory.Exists(Path.Combine(drv.RootDirectory.FullName, "NullMoth"))) dirs.Add(Path.Combine(drv.RootDirectory.FullName, "NullMoth")); }
                catch (Exception) { }
            }
            var lines = new List<string>();
            int rc = await Engine.Run("p1401.nullmoth update " + string.Join(" ", dirs.Select(Engine.Q)), l => { lock (lines) lines.Add(l); });
            ReportSaveStatus();
            busy = false; drvLink.Enabled = true;
            var text = string.Join("\r\n", lines.Where(l => !l.StartsWith("PROGRESS ")));
            MessageBox.Show(this, rc == 0 ? "The NVIDIA driver is up to date.\r\n\r\n" + text + (dirs.Count > 1 ? "" : "\r\n\r\nNo 1401 stick was plugged in; plug it in and run this again to update it too.")
                                          : "The driver could not be updated:\r\n\r\n" + text, "1401 - Update driver");
        }

        void Say(string s)
        {
            if (InvokeRequired) { BeginInvoke(new Action<string>(Say), s); return; }
            if (s.StartsWith("PROGRESS ")) { int p; var parts = s.Split(' '); if (int.TryParse(parts[1], out p)) bar.Value = Math.Max(0, Math.Min(100, p)); return; }
            log.AppendText(s + Environment.NewLine);
        }

        void Show(params Control[] on)
        {
            foreach (Control c in new Control[] { facts, bar, log, disks, refresh, guide, ocLink, logLink }) c.Visible = on.Contains(c);
            drvLink.Visible = logLink.Visible;
            firmwareLink.Visible = (page == 1 || page == 2) && firmwareGuideFile != null && File.Exists(firmwareGuideFile);
            firmwareLink.Enabled = !busy;
        }

        void Go(int p)
        {
            if (busy || p < 0 || p >= Steps.Length) return;
            page = p;
            for (int i = 0; i < Steps.Length; i++)
            {
                side[i].ForeColor = i == page ? Theme.Purple : (i < page ? Theme.Cyan : Theme.Muted);
                side[i].Font = i == page ? new Font("Verdana", 9.75f, FontStyle.Bold) : Theme.Body;
            }
            title.Text = Steps[page]; back.Enabled = page > 0 && page < Steps.Length - 1; next.Text = "Continue >";
            switch (page)
            {
                case 0:
                    note.Text = "The 1401 Assistant helps you install macOS on this PC, the way Boot Camp put Windows on a Mac.\r\n\r\n" +
                        "It checks this PC, builds the startup files macOS needs for your exact hardware, shows BIOS settings based on your scan and startup files, " +
                        "and makes a macOS install stick. Windows stays as it is. Nothing about this PC is sent anywhere.\r\n\r\n" +
                        "You need: an internet connection and a USB stick of 4 GB or more that can be erased.\r\n\r\n" +
                        "1401 is new and may not work on every PC. If it does not work on yours, set up OpenCore by hand with the guide below; " +
                        "the NullMoth app works on any OpenCore setup.";
                    Show(ocLink, logLink); var miss = Engine.Missing(); if (miss != null) { note.Text = miss; next.Enabled = false; } else next.Enabled = true;
                    break;
                case 1:
                    note.Text = scanned ? "This PC was checked. Continue, or check again." : "1401 reads this PC's hardware (processor, board, graphics, network, storage) and its ACPI tables. This takes about a minute.";
                    next.Text = scanned ? "Continue >" : "Check this PC"; Show(facts, log); next.Enabled = true; break;
                case 2:
                    note.Text = built ? summary.Split(new[] { "\r\n" }, StringSplitOptions.None)[0] : "1401 now picks the newest macOS your hardware runs and builds the startup files (OpenCore EFI) for it, then checks them with OpenCore's own validator. Downloads OpenCore and drivers.";
                    next.Text = built ? "Continue >" : "Build"; Show(facts, log); next.Enabled = scanned;
                    if (built) { log.Text = summary; log.SelectionStart = 0; log.ScrollToCaret(); }
                    break;
                case 3:
                    if (showingPrerequisites)
                    {
                        title.Text = "Firmware prerequisites";
                        note.Text = "Review storage requirements before building. No EFI or firmware changes are made by this page. Return to the check or build when finished.";
                        Show(guide); next.Enabled = true; next.Text = "Return >";
                        if (firmwareGuideFile != null && File.Exists(firmwareGuideFile)) guide.Navigate(firmwareGuideFile);
                    }
                    else
                    {
                        note.Text = "These BIOS suggestions follow your scan and startup files. Check menu names in the exact board manual, then take a photo before restarting.";
                        Show(guide); next.Enabled = built;
                        if (guideFile != null && File.Exists(guideFile)) guide.Navigate(guideFile);
                    }
                    break;
                case 4:
                    note.Text = "Plug in the USB stick that will become the macOS installer. EVERYTHING on it is erased.\r\n" +
                        "1401 downloads macOS from Apple onto it and adds the startup files" + (summary.Contains("NVIDIA") ? " and the NullMoth NVIDIA driver." : ".");
                    next.Text = written ? "Continue >" : "Erase and create"; Show(disks, refresh, bar, log); next.Enabled = true; FillDisks(); break;
                case 5:
                    note.Text = "The macOS stick is ready.\r\n\r\n1. Restart and open your board's boot menu (the key is in your BIOS steps), then choose the stick.\r\n" +
                        "2. In the 1401 boot menu choose \"Install macOS\" and follow Apple's installer.\r\n" +
                        "3. When macOS is running, open the NullMoth folder on the stick and run 1401.app to finish the NVIDIA driver.";
                    next.Text = "Close"; Show(); next.Enabled = true; break;
            }
        }

        async Task PrepareFirmwareGuide()
        {
            firmwareGuideFile = null;
            if (!scanned || scanDir == null || scanRunId == null) return;
            var target = Path.Combine(Engine.Work, "Firmware-prerequisites-" + scanRunId + ".html");
            busy = true; next.Enabled = false;
            try
            {
                int rc = await Engine.Run("p1401.guide --bios-only " + Engine.Q(Path.Combine(scanDir, "Report.json")) +
                    " --run-id " + scanRunId + " --html " + Engine.Q(target), Say);
                    ReportSaveStatus();
                if (rc == 0 && File.Exists(target)) firmwareGuideFile = target;
                else Say("Firmware review could not be generated. No EFI or firmware was changed. The build refusal still includes storage preparation guidance.");
            }
            catch (Exception) { Say("Firmware review is unavailable. No EFI or firmware was changed; use the storage guidance in the build refusal."); }
            finally { busy = false; next.Enabled = true; }
        }

        async void OnNext()
        {
            if (busy) return;
            if (page == 3 && showingPrerequisites)
            {
                showingPrerequisites = false; Go(prerequisiteReturnPage); return;
            }
            if (page == 0) { Go(1); return; }
            if (page == 1 && !scanned)
            {
                busy = true; next.Enabled = false; log.Clear();
                scanRunId = Guid.NewGuid().ToString("N");
                scanDir = ScanEvidence.RunDirectory(Engine.Work, scanRunId);
                ScanEvidence.Remember(Engine.Work, scanRunId);
                Say("Checking this PC...");
                var scanLines = new List<string>();
                int rc = await Engine.Run("p1401.scan " + Engine.Q(scanDir) + " --run-id " + scanRunId, l => { scanLines.Add(l); Say(l); });
                ReportSaveStatus();
                busy = false; next.Enabled = true;
                if (rc != 0)
                {
                    Say("The check failed. The lines above say why.");
                    OfferOperationReport("check");
                    return;
                }
                scanned = true; LoadFacts(); await PrepareFirmwareGuide(); Say("Done."); Go(1); return;
            }
            if (page == 2 && !built)
            {
                busy = true; next.Enabled = false; log.Clear();
                efiDir = Path.Combine(Engine.Work, "efi");
                var rep = Path.Combine(scanDir, "Report.json"); var acpi = Path.Combine(scanDir, "ACPI");
                var lines = new List<string>();
                Say("Building the startup files for this PC...");
                int rc = await Engine.Run("p1401 build " + Engine.Q(rep) + " " + Engine.Q(acpi) + " " + Engine.Q(efiDir) + " --json", l => { lines.Add(l); });
                ReportSaveStatus();
                busy = false; next.Enabled = true;
                var json = string.Join("\n", lines.SkipWhile(l => !l.TrimStart().StartsWith("{")));
                try
                {
                    var r = new JavaScriptSerializer { MaxJsonLength = int.MaxValue }.Deserialize<Dictionary<string, object>>(json);
                    if (rc != 0 || !(r["ok"] is bool) || !(bool)r["ok"])
                    {
                        object error;
                        var detail = r.TryGetValue("error", out error) ? "" + error : "";
                        Say("The build stopped: " + (string.IsNullOrWhiteSpace(detail) ? "Engine exit code " + rc + "." : detail));
                        // the whole engine output, so a user can post it in a bug report
                        OfferOperationReport("build");
                        return;
                    }
                    var mv = "" + r["macos_version"]; macosFull = mv; darwin = mv.Split('.')[0];
                    var notices = r["notices"] as System.Collections.ArrayList;
                    summary = "macOS " + MacName(darwin) + " for this PC, as a " + r["smbios"] + ". The startup files passed OpenCore's own check.";
                    if (notices != null) foreach (var n in notices) if (IsSupportNotice("" + n)) summary += "\r\n" + n;
                    built = true; showingPrerequisites = false;
                }
                catch (Exception e) { Say("Could not read the build result (" + e.GetType().Name + "). The saved operation report includes the engine output."); foreach (var l in lines.Take(40)) Say(l); OfferOperationReport("build"); return; }
                guideFile = Path.Combine(Engine.Work, "BIOS-steps.html");
                await Engine.Run("p1401.guide " + Engine.Q(rep) + " " + Engine.Q(Path.Combine(efiDir, "EFI", "OC", "config.plist")) + " --macos " + macosFull + " --html " + Engine.Q(guideFile), Say);
                ReportSaveStatus();
                Say("Done."); Go(2); return;
            }
            if (page == 4 && !built) { Go(2); return; }
            if (page == 4 && !written)
            {
                var d = disks.SelectedItem as UsbDisk;
                if (d == null) { MessageBox.Show(this, "Plug in a USB stick and press Refresh.", "1401"); return; }
                var ok = MessageBox.Show(this, "Erase " + d + " and make it the macOS installer?\r\n\r\nEverything on it will be lost.",
                    "1401 - erase this stick?", MessageBoxButtons.YesNo, MessageBoxIcon.Warning, MessageBoxDefaultButton.Button2);
                if (ok != DialogResult.Yes) return;
                busy = true; next.Enabled = false; refresh.Enabled = false; log.Clear(); bar.Value = 0;
                var args = "p1401.usbwriter write " + d.Number + " " + Engine.Q(efiDir) + " " + darwin;
                var pkg = Directory.Exists(Engine.NullMothDir) ? Directory.GetFiles(Engine.NullMothDir, "nullmoth-nvidia-*.tar.gz").FirstOrDefault() : null;
                if (pkg != null) args += " --driver " + Engine.Q(pkg);
                var mac = Directory.Exists(Engine.NullMothDir) ? Directory.GetFiles(Engine.NullMothDir, "1401-Mac-*.zip").FirstOrDefault() : null;
                if (mac != null) args += " --extra " + Engine.Q(mac);
                var report = Path.Combine(scanDir, "Report.json");
                if (File.Exists(report)) args += " --profile " + Engine.Q(report);
                if (d.Size > 256UL * 1024 * 1024 * 1024) args += " --allow-large";
                int rc = await Engine.Run(args, Say);
                ReportSaveStatus();
                busy = false; next.Enabled = true; refresh.Enabled = true;
                if (rc != 0) { Say("Writing the stick did not finish. The saved report includes the writer output; partial changes to the selected stick may remain."); OfferOperationReport("write"); return; }
                written = true; bar.Value = 100; Go(5); return;
            }
            if (page == 5) { Close(); return; }
            Go(page + 1);
        }

        // A folder left by an earlier run may hold read-only files; clear the flag first, and if Windows still holds it, use a fresh name
        void Wipe(string dir)
        {
            if (!Directory.Exists(dir)) return;
            try
            {
                foreach (var f in Directory.GetFileSystemEntries(dir, "*", SearchOption.AllDirectories)) File.SetAttributes(f, FileAttributes.Normal);
                Directory.Delete(dir, true);
            }
            catch (Exception) { Directory.Move(dir, dir + "-old-" + DateTime.Now.Ticks); }
        }

        void LoadFacts()
        {
            facts.Items.Clear();
            try
            {
                var r = new JavaScriptSerializer { MaxJsonLength = int.MaxValue }.Deserialize<Dictionary<string, object>>(File.ReadAllText(Path.Combine(scanDir, "Report.json")));
                Action<string, string> add = (k, v) => facts.Items.Add(new ListViewItem(new[] { k, v }));
                var mb = r.ContainsKey("Motherboard") ? r["Motherboard"] as Dictionary<string, object> : null;
                if (mb != null) add("Board", "" + mb["Name"]);
                var cpu = r.ContainsKey("CPU") ? r["CPU"] as Dictionary<string, object> : null;
                if (cpu != null) add("Processor", "" + (cpu.ContainsKey("Processor Name") ? cpu["Processor Name"] : cpu["Manufacturer"]));
                var gpu = r.ContainsKey("GPU") ? r["GPU"] as Dictionary<string, object> : null;
                if (gpu != null) foreach (var g in gpu) add("Graphics", g.Key);
                var net = r.ContainsKey("Network") ? r["Network"] as Dictionary<string, object> : null;
                if (net != null) foreach (var n in net) add("Network", n.Key);
            }
            catch (Exception e) { Say("Could not read the report: " + e.Message); }
        }

        string Self()
        {
            var root = Path.GetPathRoot(Application.ExecutablePath) ?? "";
            return root.Length >= 2 ? root.Substring(0, 2).ToUpperInvariant() : "";
        }

        // WAS synchronous on the UI thread: Windows' storage WMI provider can take tens of seconds (card readers, sleeping
        // drives), and the whole page froze with a busy cursor ("I can't do anything on that page", 10-07). It now runs on a
        // worker with a 30 s bound. It also hid every stick under 15 GB while the writer needs 2 GiB (1401 writes Apple's ~1 GB
        // recovery image, not the full installer), so 8 GB sticks read as "not detected". The floor now matches usbwriter.MIN_DISK.
        const ulong MinStick = 2UL * 1024 * 1024 * 1024;

        async void FillDisks()
        {
            if (listing) return;
            listing = true; disks.Items.Clear(); refresh.Enabled = false; bool nextWas = next.Enabled; next.Enabled = false;
            Say("Looking for USB sticks...");
            var skipped = new List<string>(); List<UsbDisk> found = null; string err = null;
            var self = Self();
            var t = Task.Run(() => Disks.ListUsb(skipped));
            if (await Task.WhenAny(t, Task.Delay(30000)) != t)
                err = "Windows did not answer the USB disk list within 30 seconds. Unplug card readers and other USB drives, then press Refresh.";
            else if (t.IsFaulted) err = "Could not list USB sticks: " + t.Exception.GetBaseException().Message;
            else found = t.Result;
            var why = new List<string>(t.IsCompleted && !t.IsFaulted ? skipped : new List<string>());
            foreach (var d in found ?? new List<UsbDisk>())
            {
                if (self.Length == 2 && d.Letters.ToUpperInvariant().Contains(self)) { why.Add(d + ": 1401 is running from it"); continue; }
                if (d.Size < MinStick) { why.Add(d + ": too small, 1401 needs 2 GB"); continue; }
                disks.Items.Add(d);
            }
            if (err != null) Say(err);
            if (disks.Items.Count > 0) { disks.SelectedIndex = 0; Say("Found " + disks.Items.Count + " USB stick(s)."); }
            else if (err == null)
            {
                Say("No USB stick found. Plug one in (4 GB or more, not the stick 1401 runs from) and press Refresh.");
                if (why.Count > 0) { Say("Disks 1401 saw and left out:"); foreach (var w in why) Say("  " + w); }
            }
            listing = false; refresh.Enabled = !busy; if (page == 4) next.Enabled = nextWas && !busy;
        }

        // A failed build sends its log to nullmothsystems.com (the same /api/upload the site's report form uses), but only
        // after the user sees what it is and clicks Send. The Windows user name and PC name are removed first.
        static List<string> Redact(List<string> lines, string error)
        {
            var user = Environment.UserName ?? ""; var pc = Environment.MachineName ?? "";
            var home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile) ?? "";
            Func<string, string> clean = t =>
            {
                if (home.Length > 3) t = t.Replace(home, "%USERPROFILE%");
                if (user.Length > 2) t = t.Replace(user, "user");
                if (pc.Length > 2) t = t.Replace(pc, "this-pc");
                return t;
            };
            var o = new List<string> { "1401 " + Application.ProductVersion + " build log", "error: " + clean(error), "" };
            o.AddRange(lines.Select(clean));
            return o;
        }

        void ReportSaveStatus()
        {
            if (Engine.LastReport != null && !Engine.LastReport.Saved)
                Say(Engine.LastReport.Failure + " The operation output may remain visible, but a durable final report is unavailable.");
        }

        void OfferOperationReport(string kind)
        {
            var report = Engine.LastReport;
            if (report == null || !report.Saved)
            {
                Say(report == null ? "The operation has no saved local report. The visible output remains available to copy." : report.Failure);
                return;
            }
            Say("The local report is saved at " + report.Path + ". Scan for logs and send them can retry after restart.");
            OfferLog(report.Path, kind);
        }

        void OfferLog(string file, string kind)
        {
            var ask = MessageBox.Show(this,
                "The " + kind + " failed.\r\n\r\n1401 is sending this log to nullmothsystems.com so the bug can be found and fixed. " +
                "It holds this scan's hardware list, bounded device/CPU observations and what the check or build printed. Windows capabilities do not establish macOS support. Your Windows user name and PC name are removed first. " +
                "Nothing else on this PC is sent.\r\n\r\nClick OK to send it now, or Cancel to keep it only on this PC.",
                "1401 - sending the log", MessageBoxButtons.OKCancel, MessageBoxIcon.Information, MessageBoxDefaultButton.Button1);
            if (ask != DialogResult.OK) { Say("The log was not sent. It stays in " + file + "."); return; }
            var ids = new List<string>();
            var batch = NewBatch();
            var id = Send(file, "1401-" + kind + "-log.txt", kind + " failed", batch);
            if (id != null) ids.Add(id);
            var evidence = ScanEvidence.Find(Engine.Work, scanRunId, false);
            if (evidence != null) {
                var receipt = Send(evidence.Path, "1401-scan-evidence.json.txt", kind + " failed; saved evidence from this scan run; macOS support not assessed", batch);
                if (receipt != null) ids.Add(receipt);
            }
            Say(ids.Count > 0 ? "Logs sent. Report IDs " + string.Join(", ", ids) + " - mention them in the NullMoth Discord if you ask for help."
                             : "Could not send the logs (" + lastSendError + "). They stay on this PC.");
        }

        // POST one text file to the site's upload endpoint; returns the report ID, or null when it could not be sent.
        string lastSendError = "";

        // One random value per send: every file of one send shares it, so the site can tell one run's build log, stick
        // config and startup logs apart from every other user's. It names the run, not the PC: a new one each time.
        internal static string NewBatch()
        {
            var b = new byte[8];
            using (var r = System.Security.Cryptography.RandomNumberGenerator.Create()) r.GetBytes(b);
            return "1401-app-" + BitConverter.ToString(b).Replace("-", "").ToLowerInvariant();
        }

        // POST one text file to the site's upload endpoint; returns the report ID, or null (reason in lastSendError).
        string Send(string file, string sendName, string what, string batch = null)
        {
            lastSendError = "";
            try
            {
                System.Net.ServicePointManager.SecurityProtocol |= System.Net.SecurityProtocolType.Tls12;
                var body = File.ReadAllBytes(file);
                // the site refuses a "text log" with NUL bytes; OpenCore's file log can carry padding NULs at the end
                if (sendName.EndsWith(".txt", StringComparison.OrdinalIgnoreCase)) body = body.Where(b => b != 0).ToArray();
                string sha;
                using (var h = System.Security.Cryptography.SHA256.Create())
                    sha = BitConverter.ToString(h.ComputeHash(body)).Replace("-", "").ToLowerInvariant();
                // serialized, not concatenated: the notes can now carry what the user typed (quotes, backslashes)
                var notes = "1401 " + Application.ProductVersion + " " + what + " (sent from the app)";
                if (notes.Length > 3900) notes = notes.Substring(0, 3900);
                var meta = new JavaScriptSerializer().Serialize(new Dictionary<string, object> {
                    { "consent", true }, { "notes", notes }, { "batch", batch ?? NewBatch() } });
                var b64 = Convert.ToBase64String(System.Text.Encoding.UTF8.GetBytes(meta)).TrimEnd('=').Replace('+', '-').Replace('/', '_');
                var req = (System.Net.HttpWebRequest)System.Net.WebRequest.Create("https://nullmothsystems.com/api/upload");
                req.Method = "POST"; req.ContentType = "application/octet-stream"; req.Timeout = 30000;
                req.Headers.Add("X-File-Name", Uri.EscapeDataString(sendName));
                req.Headers.Add("X-Meta", b64);
                req.Headers.Add("X-Content-SHA256", sha);   // the server refuses the upload if the bytes it got differ
                using (var st = req.GetRequestStream()) st.Write(body, 0, body.Length);
                using (var resp = (System.Net.HttpWebResponse)req.GetResponse())
                using (var rd = new StreamReader(resp.GetResponseStream()))
                {
                    var j = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(rd.ReadToEnd());
                    if (j.ContainsKey("sha256") && ("" + j["sha256"]) != sha) { lastSendError = "the server stored different bytes"; return null; }
                    return j.ContainsKey("id") ? "" + j["id"] : "?";
                }
            }
            catch (System.Net.WebException we)
            {
                lastSendError = we.Message;
                try
                {
                    using (var rd = new StreamReader(we.Response.GetResponseStream()))
                    {
                        var j = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(rd.ReadToEnd());
                        if (j.ContainsKey("error")) lastSendError = "" + j["error"];
                    }
                }
                catch (Exception) { }
                return null;
            }
            catch (Exception e) { lastSendError = e.Message; return null; }
        }

        // A PC that never reaches macOS leaves its story on the stick: OpenCore's opencore-*.txt (with Apple's boot log)
        // and macOS panic-*.txt, written by the 1401 build's Misc > Debug settings. When 1401 opens with such a stick in,
        // it sends the newest ones (after the same notice) and moves them into NullMoth\sent-logs so they go only once.
        internal static bool IsSupportNotice(string text)
        {
            return text.StartsWith("NullMoth", StringComparison.Ordinal) ||
                   text.StartsWith("Laptop display note:", StringComparison.Ordinal) ||
                   text.StartsWith("Intel I225-LM vP", StringComparison.Ordinal);
        }

        internal bool VerifySupportNoticePresentation()
        {
            summary = "Package verification\r\nLaptop display note: panel wiring requires verification.\r\nIntel I225-LM vP link testing is required.";
            built = scanned = true;
            Go(2);
            return log.Visible && log.Text == summary && log.ScrollBars == ScrollBars.Vertical;
        }

        // Executed only by the owned packaged GUI verification session. The fixture
        // exercises registered control handlers without scanning or writing a stick.
        internal string FirmwareVerificationPhase { get; private set; }

        internal bool VerifyFirmwarePrerequisiteNavigation()
        {
            int savedPage = page, savedReturn = prerequisiteReturnPage;
            bool savedScanned = scanned, savedBuilt = built, savedShowing = showingPrerequisites, savedWritten = written, savedBusy = busy;
            string savedGuide = firmwareGuideFile;
            string directory = Path.Combine(Path.GetTempPath(), "1401-firmware-ui-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(directory);
            string localGuide = Path.Combine(directory, "firmware.html");
            try
            {
                File.WriteAllText(localGuide, "<!doctype html><html><head><title>Firmware prerequisite fixture</title></head><body><h1>Firmware prerequisites</h1><p>No settings changed.</p></body></html>");
                FirmwareVerificationPhase = "missing_guide";
                busy = false; scanned = true; built = written = false; showingPrerequisites = false; firmwareGuideFile = null;
                Go(1);
                if (firmwareLink.Visible) return false;
                FirmwareVerificationPhase = "scan_link_and_local_document";
                firmwareGuideFile = localGuide;
                Go(1);
                if (!firmwareLink.Visible || !firmwareLink.Enabled || firmwareLink.Bounds.Bottom > body.ClientSize.Height) return false;
                ActivateFirmwareLinkForVerification();
                if (page != 3 || !showingPrerequisites || prerequisiteReturnPage != 1 ||
                    title.Text != "Firmware prerequisites" || next.Text != "Return >" || !guide.Visible || !next.Enabled || built) return false;
                var wait = Stopwatch.StartNew();
                while (wait.ElapsedMilliseconds < 2500 && (guide.Url == null || guide.DocumentTitle != "Firmware prerequisite fixture"))
                {
                    Application.DoEvents(); System.Threading.Thread.Sleep(10);
                }
                if (guide.Url == null || !guide.Url.IsFile || !string.Equals(guide.Url.LocalPath, localGuide, StringComparison.OrdinalIgnoreCase) ||
                    guide.DocumentTitle != "Firmware prerequisite fixture") return false;
                FirmwareVerificationPhase = "scan_next_return";
                next.PerformClick();
                if (page != 1 || showingPrerequisites || built || written || !firmwareLink.Visible) return false;
                FirmwareVerificationPhase = "scan_back_return";
                ActivateFirmwareLinkForVerification(); back.PerformClick();
                if (page != 1 || showingPrerequisites || built || written) return false;
                FirmwareVerificationPhase = "refused_build_link";
                Go(2);
                if (!firmwareLink.Visible || built) return false;
                // This is the state left by a build refusal; the link uses no successful EFI.
                ActivateFirmwareLinkForVerification();
                if (page != 3 || prerequisiteReturnPage != 2 || built) return false;
                FirmwareVerificationPhase = "refused_build_next_return";
                next.PerformClick();
                if (page != 2 || showingPrerequisites || built || written) return false;
                FirmwareVerificationPhase = "refused_build_back_return";
                ActivateFirmwareLinkForVerification(); back.PerformClick();
                if (page != 2 || showingPrerequisites || built || written) return false;
                FirmwareVerificationPhase = "successful_build_required";
                // A normal completed-EFI guide cannot advance after a refused build.
                Go(3);
                if (next.Enabled || title.Text != "Your BIOS steps" || built) return false;
                built = true; Go(3);
                if (!next.Enabled || next.Text != "Continue >" || title.Text != "Your BIOS steps") return false;
                built = false; Go(2);
                // Invoke the actual Next handler with synthetic page state; do not call
                // Go(4), which enumerates real removable disks for the normal product UI.
                FirmwareVerificationPhase = "unbuilt_usb_refusal";
                page = 4; next.PerformClick();
                if (page != 2 || built || written || disks.Visible || refresh.Visible) return false;
                FirmwareVerificationPhase = "busy_link_refusal";
                busy = true;
                ActivateFirmwareLinkForVerification();
                if (page != 2 || showingPrerequisites) return false;
                FirmwareVerificationPhase = "missing_file_link_refusal";
                busy = false; firmwareGuideFile = Path.Combine(directory, "missing.html");
                Go(2); ActivateFirmwareLinkForVerification();
                bool passed = page == 2 && !firmwareLink.Visible && !showingPrerequisites && !built && !written;
                if (passed) FirmwareVerificationPhase = "complete";
                return passed;
            }
            finally
            {
                busy = false; guide.Stop(); guide.Navigate("about:blank");
                scanned = savedScanned; built = savedBuilt; written = savedWritten; showingPrerequisites = savedShowing;
                firmwareGuideFile = savedGuide; prerequisiteReturnPage = savedReturn;
                Go(savedPage); busy = savedBusy;
                Directory.Delete(directory, true);
            }
        }

        void ActivateFirmwareLinkForVerification()
        {
            // Raise the same LinkClicked event wired by the constructor, rather than
            // reproducing its navigation decisions in a separate test implementation.
            var method = typeof(LinkLabel).GetMethod("OnLinkClicked", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic);
            if (method == null || firmwareLink.Links.Count == 0) throw new InvalidOperationException("Link activation is unavailable.");
            method.Invoke(firmwareLink, new object[] { new LinkLabelLinkClickedEventArgs(firmwareLink.Links[0]) });
        }

        internal void OfferStickLogs(bool asked)
        {
            if (IsDisposed || Disposing || !IsHandleCreated) return;
            var found = new List<string>();
            var configs = new List<string>();
            // asked from the link: the last failed build's log on this PC goes too
            {
                try { found.AddRange(DurableReport.Find(Engine.Work).Where(f => asked || Path.GetFileName(f).Contains("-crash-"))); }
                catch (Exception error) { Say("Saved reports could not be listed (" + error.GetType().Name + ", code " + error.HResult + "). Check access to the app data folder; existing files were retained."); }
            }
            var bl = Path.Combine(Engine.Work, "build-log.txt");
            if (asked && File.Exists(bl)) found.Add(bl);
            var scanLog = Path.Combine(Engine.Work, "scan-log.txt");
            if (asked && File.Exists(scanLog)) found.Add(scanLog);
            var evidence = asked ? ScanEvidence.Find(Engine.Work, scanRunId, true) : null;
            if (evidence != null) found.Insert(0, evidence.Path);
            var crash = Path.Combine(Engine.Work, "crash-log.txt");   // written by Program.cs when 1401 itself crashed
            if (File.Exists(crash)) found.Add(crash);
            foreach (var d in DriveInfo.GetDrives())
            {
                try
                {
                    if (d.DriveType != DriveType.Removable || !d.IsReady) continue;
                    found.AddRange(Directory.GetFiles(d.RootDirectory.FullName, "panic-*.txt"));
                    found.AddRange(Directory.GetFiles(d.RootDirectory.FullName, "opencore-*.txt").OrderByDescending(f => f).Take(3));
                    // 10-07: four stick logs (NM-DXKP8FQ7 ...) ended at Apple's hand-off to the kernel and named no hardware
                    // or settings, so nothing in them could be fixed. The config that booted goes with them, serials removed.
                    var cfg = Path.Combine(d.RootDirectory.FullName, "EFI", "OC", "config.plist");
                    if (found.Any(f => Path.GetPathRoot(f) == d.RootDirectory.FullName) && File.Exists(cfg))
                    {
                        var safe = Path.Combine(Engine.Work, "stick-config-" + d.Name.TrimEnd('\\', ':') + ".txt");
                        File.WriteAllText(safe, RedactConfig(File.ReadAllText(cfg)));
                        configs.Add(safe);
                    }
                }
                catch (Exception) { }
            }
            if (found.Count == 0)
            {
                if (asked) MessageBox.Show(this, "No logs were found. Plug in the USB stick 1401 made (the one you started macOS from) and try again.",
                                           "1401", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }
            found = found.Where(f => DurableReport.IsLocal(Engine.Work, f)).Concat(configs).Concat(found.Where(f => !DurableReport.IsLocal(Engine.Work, f))).Distinct().Take(6).ToList();   // the site takes 30 uploads per hour from one address
            // 10-07: most sticks now reach the macOS kernel and then stop with nothing written (a hang leaves no panic
            // file), so the line the screen stopped on is the one fact the logs cannot hold. Optional; same two clicks.
            string screen;
            var ask = AskSend(
                "1401 found " + found.Count + " diagnostic file" + (found.Count == 1 ? "" : "s") + " (available scan/build evidence and startup logs from attached sticks).\r\n\r\n" +
                "These retain available failure and hardware observations. 1401 is sending them to nullmothsystems.com so the bug can be found and fixed. " +
                "They hold what OpenCore and macOS printed while starting, and the stick's OpenCore settings with serial numbers removed. " +
                "An included scan receipt records saved Windows hardware observations, even if the check failed; it does not prove this PC or the attached stick has that hardware. Nothing else on this PC is sent.\r\n\r\nClick Send to send them now, or Cancel to keep them locally.",
                out screen);
            if (ask != DialogResult.OK) return;
            var what = "startup log from the stick" + (screen.Length > 0 ? "; screen stopped at: " + screen : "");
            var ids = new List<string>();
            var batch = NewBatch();
            foreach (var f in found)
            {
                var localWhat = DurableReport.IsLocal(Engine.Work, f) ? "saved local operation report; original app version is recorded in the payload; not current-PC identity proof" : what;
                var id = Send(f, Path.GetFileName(f).EndsWith(".json", StringComparison.OrdinalIgnoreCase) ? Path.GetFileName(f) + ".txt" : Path.GetFileName(f), localWhat + (evidence != null && f == evidence.Path ? (evidence.CurrentRun ? "; this scan run; not macOS qualification" : "; saved prior scan; not current-PC or attached-stick identity proof") : ""), batch);
                if (id == null) continue;
                ids.Add(id);
                try
                {
                    if (f == bl || f == scanLog || DurableReport.IsLocal(Engine.Work, f) || (evidence != null && f == evidence.Path) || configs.Contains(f)) continue;
                    if (f == crash) { File.Move(crash, crash + ".sent-" + DateTime.Now.ToString("yyyyMMdd-HHmmss")); continue; }
                    var sent = Path.Combine(Path.GetPathRoot(f), "NullMoth", "sent-logs"); Directory.CreateDirectory(sent);
                    File.Move(f, Path.Combine(sent, Path.GetFileName(f)));
                }
                catch (Exception) { }
            }
            MessageBox.Show(this, ids.Count > 0 ? "Sent " + ids.Count + " log(s). Report ID " + string.Join(", ", ids) + " - mention it in the NullMoth Discord if you ask for help."
                                                : "The logs could not be sent: " + lastSendError + "\r\nThey are still where they were; try again with Scan for logs and send them.",
                            "1401", MessageBoxButtons.OK, MessageBoxIcon.Information);
        }

        // The Mac identity OpenCore gives this PC (serial, board serial, UUID, ROM) is the only personal part of a config.
        static string RedactConfig(string xml)
        {
            // <data> must stay valid base64 or the uploaded config no longer parses as a plist (10-07: every 1.0.5 copy)
            const string keys = @"(<key>(SystemSerialNumber|MLB|BoardSerialNumber|ChassisSerialNumber|SystemUUID|ROM|SerialNumber)</key>\s*";
            xml = System.Text.RegularExpressions.Regex.Replace(xml, keys + @"<string>)[^<]*(</string>)", "${1}REMOVED${3}");
            return System.Text.RegularExpressions.Regex.Replace(xml, keys + @"<data>)[^<]*(</data>)", "${1}AAAAAAAA${3}");
        }

        DialogResult AskSend(string text, out string screen)
        {
            using (var f = new Form { AutoScaleDimensions = new SizeF(96F, 96F), AutoScaleMode = AutoScaleMode.Dpi,
                                      Text = "1401 - sending the startup logs", FormBorderStyle = FormBorderStyle.FixedDialog,
                                      MaximizeBox = false, MinimizeBox = false, StartPosition = FormStartPosition.CenterParent,
                                      ClientSize = new Size(520, 300), Font = Theme.Body })
            {
                f.SuspendLayout();
                var msg = new Label { Text = text, Left = 14, Top = 12, Width = 492, Height = 150 };
                var q = new Label { Text = "Optional: the last line on the screen when it stopped (for example \"PCI configuration begin\"):",
                                    Left = 14, Top = 168, Width = 492, Height = 34 };
                var box = new TextBox { Left = 14, Top = 204, Width = 492, MaxLength = 300 };
                var send = new Button { Text = "Send", DialogResult = DialogResult.OK, Left = 330, Top = 252, Width = 84 };
                var cancel = new Button { Text = "Cancel", DialogResult = DialogResult.Cancel, Left = 422, Top = 252, Width = 84 };
                f.Controls.AddRange(new Control[] { msg, q, box, send, cancel });
                f.AcceptButton = send; f.CancelButton = cancel;
                f.ResumeLayout(false); f.PerformLayout();
                var r = f.ShowDialog(this);
                screen = (box.Text ?? "").Replace("\r", " ").Replace("\n", " ").Trim();
                return r;
            }
        }

        static string MacName(string d)
        {
            switch (d) { case "25": return "Tahoe"; case "24": return "Sequoia"; case "23": return "Sonoma"; case "22": return "Ventura"; case "21": return "Monterey"; default: return d; }
        }
    }
}
