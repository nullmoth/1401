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
        // Every step title goes through Loc: the sidebar and the page heading are the same string,
        // so the nav can't drift from the page. Untranslated steps fall back to the English wording.
        static readonly string[] Steps = { "Introduction", "Check this PC", "Build the Mac setup", "Your BIOS steps", "Create the macOS stick", "Done" };
        int page;
        readonly Label[] side = new Label[Steps.Length];
        readonly GlassPanel body = new GlassPanel();
        readonly GlassPanel foot = new GlassPanel();
        readonly GlassPanel nav = new GlassPanel();
        readonly Label headTitle = new Label();
        readonly Timer sky = new Timer { Interval = 100 };
        readonly Label title = new Label(), note = new Label();
        readonly Button back = new Button(), next = new Button();
        readonly TextBox log = new TextBox();
        readonly ProgressBar bar = new ProgressBar();
        readonly ComboBox disks = new ComboBox();
        // The macOS the user picks: index 0 = macOS 15 Sequoia (Darwin 24), 1 = macOS 26 Tahoe (Darwin 25).
        readonly ComboBox osPick = new ComboBox();
        // Off unless the user ticks it: the community AMD RDNA 4 display driver and the MediaTek Wi-Fi driver are
        // unproven on most of the hardware they claim, and each takes over something the machine needs to be usable.
        readonly CheckBox expDrivers = new CheckBox();
        readonly Button refresh = new Button();
        readonly WebBrowser guide = new WebBrowser();
        readonly LinkLabel ocLink = new LinkLabel();
        readonly LinkLabel logLink = new LinkLabel(), coffeeLink = new LinkLabel(), creditsLink = new LinkLabel();
        readonly LinkLabel drvLink = new LinkLabel();
        readonly LinkLabel appLink = new LinkLabel();
        readonly LinkLabel doctorLink = new LinkLabel();
        readonly LinkLabel firmwareLink = new LinkLabel();
        readonly ListView facts = new ListView();
        bool busy, scanned, built, written, listing, showingPrerequisites;
        // The newest 1401 when this one is older (startup check), else null. 10-12: 61% of a day's 170 failed writes came
        // from versions whose bugs were already fixed (1.1.0 alone: 59), so an old 1401 updates before it builds anything.
        string mustUpdate;
        // Startup logs the last build read, and drive roots it must also read (the picked stick, which may not be Removable).
        readonly HashSet<string> buildLogFiles = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        readonly List<string> stickRoots = new List<string>();
        int prerequisiteReturnPage = 1;
        string firmwareGuideFile;
        string scanDir, scanRunId, efiDir, guideFile, darwin = "24", macosFull = "24.99.99", summary = "";

        public MainForm(bool verificationMode = false)
        {
            // Every bound below is in 96-DPI pixels. On a 150-200 % display (most 4K screens and many laptops) the
            // point-sized fonts grew with the display while the boxes kept their 96-DPI size, so text was cut off.
            // Scale the whole layout with the display, as the Windows Forms designer does for its own forms.
            SuspendLayout();
            // the palette first, so every control below is built in the colours the user last chose
            Glass.LoadPreference(); Theme.Use(Glass.Light);
            DoubleBuffered = true;
            AutoScaleDimensions = new SizeF(96F, 96F); AutoScaleMode = AutoScaleMode.Dpi;
            Text = Loc.T("1401 Assistant");
            Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
            ClientSize = new Size(900, 620);
            FormBorderStyle = FormBorderStyle.Sizable; MaximizeBox = true; MinimumSize = new Size(640, 420);
            BackColor = Theme.DeskBg; ForeColor = Theme.Text; Font = Theme.Body;
            StartPosition = FormStartPosition.CenterScreen;
            Shown += (o, e) => FitToWorkingArea();
            if (!verificationMode) Shown += (o, e) => OfferStickLogs(false);
            if (!verificationMode) Shown += (o, e) => CheckAppVersion();

            // The striped glass title bar: "1401 - <step>" and the light/dark switch; Windows keeps its own window buttons.
            var head = new GlassPanel { Dock = DockStyle.Top, Height = 44, BackColor = Color.Transparent, Stripes = true };
            head.Tint = () => Theme.BarTint;
            headTitle.Font = new Font(Theme.Face("Times New Roman"), 13f, FontStyle.Bold); headTitle.ForeColor = Theme.Text;
            headTitle.BackColor = Color.Transparent; headTitle.AutoSize = true; headTitle.Location = new Point(16, 11);
            headTitle.Text = "1401 — " + Loc.T(Steps[0]);
            var themeSwitch = new ThemeSwitch { Anchor = AnchorStyles.Top | AnchorStyles.Right };
            themeSwitch.Location = new Point(ClientSize.Width - themeSwitch.Width - 16, 10);
            themeSwitch.Toggled += (o, e) => { Glass.SetLight(this, !Glass.Light); nav.Invalidate(true); };
            head.Controls.AddRange(new Control[] { headTitle, themeSwitch });

            nav.Dock = DockStyle.Left; nav.Width = 220; nav.BackColor = Color.Transparent; nav.Padding = new Padding(12, 16, 8, 8);
            nav.Tint = () => Theme.GlassTint;
            for (int i = Steps.Length - 1; i >= 0; i--)
            {
                side[i] = new Label { Text = "  " + (i + 1) + ".  " + Loc.T(Steps[i]), Dock = DockStyle.Top, Height = 38, Font = Theme.Body,
                                      ForeColor = Theme.Muted, BackColor = Color.Transparent, TextAlign = ContentAlignment.MiddleLeft };
                nav.Controls.Add(side[i]);
            }
            // the current step sits on a rounded highlight, as in the Mac app's sidebar
            nav.Paint += (o, e) =>
            {
                if (side[page] == null) return;
                var r = side[page].Bounds; r.Inflate(-2, -3);
                e.Graphics.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
                using (var path = Glass.Round(r, 9))
                using (var fill = new SolidBrush(Color.FromArgb(Glass.Light ? 40 : 90, Theme.Purple2)))
                using (var edge = new Pen(Theme.Purple))
                { e.Graphics.FillPath(fill, path); e.Graphics.DrawPath(edge, path); }
            };

            foot.Dock = DockStyle.Bottom; foot.Height = 56; foot.BackColor = Color.Transparent; foot.Tint = () => Theme.BarTint;
            back.Text = Loc.T("< Back"); back.Bounds = new Rectangle(560, 12, 150, 32); Theme.Style(back, false);
            next.Text = Loc.T("Continue >"); next.Bounds = new Rectangle(720, 12, 160, 32); Theme.Style(next);
            back.Click += (s, e) => {
                if (page == 3 && showingPrerequisites) { showingPrerequisites = false; Go(prerequisiteReturnPage); }
                else Go(page - 1);
            }; next.Click += (s, e) => OnNext();
            foot.Controls.AddRange(new Control[] { back, next });

            body.Dock = DockStyle.Fill; body.Padding = new Padding(24, 18, 24, 12); body.BackColor = Color.Transparent; body.AutoScroll = true;
            body.Tint = () => Glass.Light ? Color.FromArgb(120, 250, 247, 255) : Color.FromArgb(105, 8, 3, 16);
            title.Font = Theme.Title; title.ForeColor = Theme.Text; title.AutoSize = false;
            note.AutoSize = true; note.AutoEllipsis = false; note.ForeColor = Theme.Text;
            log.Multiline = true; log.ReadOnly = true; log.ScrollBars = ScrollBars.Vertical; log.BackColor = Theme.LogBg;
            log.ForeColor = Theme.Cyan; log.Font = Theme.Log; log.BorderStyle = BorderStyle.FixedSingle;
            log.Bounds = new Rectangle(24, 330, 620, 140);
            bar.Bounds = new Rectangle(24, 300, 620, 18);
            facts.View = View.Details; facts.FullRowSelect = true; facts.HeaderStyle = ColumnHeaderStyle.Nonclickable;
            facts.BackColor = Theme.Panel; facts.ForeColor = Theme.Text; facts.Font = Theme.Fact;
            facts.Columns.Add("", 170); facts.Columns.Add("", 440); facts.Bounds = new Rectangle(24, 156, 620, 136);
            disks.DropDownStyle = ComboBoxStyle.DropDownList; disks.Bounds = new Rectangle(24, 170, 500, 28);
            disks.BackColor = Theme.Panel; disks.ForeColor = Theme.Text; disks.Font = Theme.Picker;
            refresh.Text = Loc.T("Refresh"); refresh.Bounds = new Rectangle(534, 168, 110, 30); Theme.Style(refresh, false);
            refresh.Click += (s, e) => FillDisks();
            osPick.DropDownStyle = ComboBoxStyle.DropDownList; osPick.Width = 300;
            osPick.BackColor = Theme.Panel; osPick.ForeColor = Theme.Text; osPick.Font = Theme.Picker;
            osPick.Items.AddRange(new object[] { Loc.T("macOS 15 Sequoia"), Loc.T("macOS 26 Tahoe") }); osPick.SelectedIndex = 0;
            // A different pick needs different startup files: drop the finished build so Build runs again.
            osPick.SelectedIndexChanged += (s, e) => { if (built && !busy) { built = false; summary = ""; Go(2); } };
            expDrivers.Text = Loc.T("Include experimental drivers (Wi-Fi, AMD RDNA 4 graphics, USB and power fixes)");
            expDrivers.AutoSize = true; expDrivers.Checked = false;
            expDrivers.BackColor = Color.Transparent; expDrivers.ForeColor = Theme.Text; expDrivers.Font = Theme.Picker;
            // Including them changes which kexts the build carries, so a finished build is no longer the right one.
            expDrivers.CheckedChanged += (s, e) => { if (built && !busy) { built = false; summary = ""; Go(2); } };
            guide.ScriptErrorsSuppressed = true;
            ocLink.Text = Loc.T("OpenCore Install Guide (dortania.github.io/OpenCore-Install-Guide)"); ocLink.AutoSize = true;
            ocLink.LinkColor = Theme.Cyan; ocLink.Font = Theme.Link;
            ocLink.LinkClicked += (s, e) => System.Diagnostics.Process.Start("https://dortania.github.io/OpenCore-Install-Guide/");
            logLink.Text = Loc.T("Something went wrong? Scan for logs and send them"); logLink.AutoSize = true;
            logLink.LinkColor = Theme.Cyan; logLink.Font = Theme.Link;
            logLink.LinkClicked += (s, e) => OfferStickLogs(true);
            coffeeLink.Text = Loc.T("Buy me a coffee"); coffeeLink.AutoSize = true;
            coffeeLink.LinkColor = Theme.Cyan; coffeeLink.Font = Theme.Link;
            coffeeLink.LinkClicked += (s, e) => System.Diagnostics.Process.Start("https://buymeacoffee.com/nullmoth");
            // Every project 1401 is built on or downloads, with its author and licence (NOTICE.md in the package).
            creditsLink.Text = Loc.T("Credits"); creditsLink.AutoSize = true;
            creditsLink.LinkColor = Theme.Cyan; creditsLink.Font = Theme.Link;
            creditsLink.LinkClicked += (s, e) =>
            {
                var notice = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "engine", "app", "NOTICE.md");
                if (File.Exists(notice)) System.Diagnostics.Process.Start("notepad.exe", "\"" + notice + "\"");
                else System.Diagnostics.Process.Start("https://github.com/nullmoth/1401/blob/main/NOTICE.md");
            };
            drvLink.Text = Loc.T("Update the NVIDIA driver (newest release, here and on your 1401 stick)"); drvLink.AutoSize = true;
            drvLink.LinkColor = Theme.Cyan; drvLink.Font = Theme.Link;
            drvLink.LinkClicked += (s, e) => UpdateDriver();
            appLink.Text = Loc.T("Update 1401 (this app)"); appLink.AutoSize = true;
            appLink.LinkColor = Theme.Cyan; appLink.Font = Theme.Link;
            appLink.LinkClicked += (s, e) => UpdateApp();
            doctorLink.Text = Loc.T("Built your own EFI? Check it (and fix it) with the same rules 1401 uses"); doctorLink.AutoSize = true;
            doctorLink.LinkColor = Theme.Cyan; doctorLink.Font = Theme.Link;
            doctorLink.LinkClicked += (s, e) => CheckOwnEfi();
            firmwareLink.Text = Loc.T("Review firmware prerequisites"); firmwareLink.AutoSize = true;
            firmwareLink.LinkColor = Theme.Cyan; firmwareLink.Font = Theme.Link;
            firmwareLink.LinkClicked += (s, e) => {
                if (busy || firmwareGuideFile == null || !File.Exists(firmwareGuideFile)) return;
                prerequisiteReturnPage = page; showingPrerequisites = true; Go(3);
            };
            body.Controls.AddRange(new Control[] { title, note, facts, bar, log, disks, refresh, osPick, expDrivers, guide, ocLink, logLink, coffeeLink, creditsLink, drvLink, appLink, doctorLink, firmwareLink });

            Controls.Add(body); Controls.Add(nav); Controls.Add(foot); Controls.Add(head);
            // The stars drift: ten frames a second repaint the glass panels and the see-through text on them, never the
            // list, log or web view (those are opaque and would only flicker).
            sky.Tick += (o, e) =>
            {
                foreach (var pane in new Control[] { head, nav, foot }) pane.Invalidate(true);
                body.Invalidate(false);
                foreach (Control c in body.Controls) if (c.Visible && c.BackColor == Color.Transparent) c.Invalidate();
            };
            sky.Start();
            FormClosed += (o, e) => sky.Stop();
            body.Resize += (s, e) => LayoutBody();
            foot.Resize += (s, e) => LayoutFooter();
            DpiChanged += (s, e) => { FitToWorkingArea(e.DeviceDpiNew); LayoutBody(); LayoutFooter(); };
            ResumeLayout(false); PerformLayout();
            Go(0);
        }

        void FitToWorkingArea(int dpi = 0)
        {
            if (!IsHandleCreated || IsDisposed) return;
            var work = Screen.FromControl(this).WorkingArea;
            float dpiScale = (dpi > 0 ? dpi : (int)CurrentAutoScaleDimensions.Width) / 96F;
            int margin = Math.Max(24, (int)Math.Round(24F * dpiScale));
            int chromeWidth = Math.Max(0, Width - ClientSize.Width);
            int chromeHeight = Math.Max(0, Height - ClientSize.Height);
            int availableOuterWidth = Math.Max(320, work.Width - margin);
            int availableOuterHeight = Math.Max(260, work.Height - margin);
            int availableClientWidth = Math.Max(320, availableOuterWidth - chromeWidth);
            int availableClientHeight = Math.Max(260, availableOuterHeight - chromeHeight);
            int minWidth = Math.Min((int)Math.Round(640F * dpiScale), availableOuterWidth);
            int minHeight = Math.Min((int)Math.Round(420F * dpiScale), availableOuterHeight);
            MinimumSize = new Size(minWidth, minHeight);
            int width = Math.Min(ClientSize.Width, availableClientWidth);
            int height = Math.Min(ClientSize.Height, availableClientHeight);
            if (width != ClientSize.Width || height != ClientSize.Height) ClientSize = new Size(width, height);
        }

        void LayoutFooter()
        {
            if (foot.IsDisposed) return;
            const int gap = 10, right = 20;
            next.Top = 12;
            next.Left = Math.Max(gap, foot.ClientSize.Width - right - next.Width);
            back.Top = 12;
            back.Left = Math.Max(gap, next.Left - gap - back.Width);
        }

        void LayoutFactsColumns(int width)
        {
            if (facts.Columns.Count < 2) return;
            int available = Math.Max(240, width - SystemInformation.VerticalScrollBarWidth);
            int first = Math.Min(Math.Max(150, available / 3), Math.Max(150, available - 180));
            facts.Columns[0].Width = first;
            facts.Columns[1].Width = Math.Max(120, available - first - 4);
        }

        void LayoutLink(LinkLabel link, int left, int top, int width, ref int cursor)
        {
            if (!link.Visible) return;
            link.AutoSize = false;
            link.MaximumSize = new Size(width, 0);
            var preferred = link.GetPreferredSize(new Size(width, 0));
            link.SetBounds(left, top, width, Math.Max(24, preferred.Height));
            cursor = link.Bottom + 8;
        }

        // Short links share a line while they fit and wrap onto the next one when the window or the font does not allow it.
        void LayoutLinkRow(int left, int width, ref int cursor, params LinkLabel[] links)
        {
            int x = left, top = cursor, rowBottom = cursor;
            foreach (var link in links)
            {
                if (!link.Visible) continue;
                link.AutoSize = true;
                link.MaximumSize = new Size(width, 0);
                var size = link.GetPreferredSize(new Size(width, 0));
                if (x > left && x + size.Width > left + width) { x = left; top = rowBottom + 8; }
                link.SetBounds(x, top, size.Width, Math.Max(24, size.Height));
                x = link.Right + 24;
                rowBottom = Math.Max(rowBottom, link.Bottom);
            }
            if (rowBottom > cursor) cursor = rowBottom + 8;
        }
        int LinkRowHeight(int width, params LinkLabel[] links)
        {
            int x = 0, height = 0, row = 0;
            foreach (var link in links)
            {
                if (!link.Visible) continue;
                link.AutoSize = true;
                link.MaximumSize = new Size(width, 0);
                var size = link.GetPreferredSize(new Size(width, 0));
                if (x > 0 && x + size.Width > width) { height += row + 8; x = 0; row = 0; }
                x += size.Width + 24;
                row = Math.Max(row, Math.Max(24, size.Height));
            }
            return row > 0 ? height + row + 8 : 0;
        }
        int LinkHeight(LinkLabel link, int width)
        {
            if (!link.Visible) return 0;
            link.AutoSize = true;
            link.MaximumSize = new Size(width, 0);
            return Math.Max(24, link.GetPreferredSize(new Size(width, 0)).Height) + 8;
        }

        void LayoutBody()
        {
            if (body.IsDisposed || body.ClientSize.Width <= 0) return;
            int left = body.Padding.Left;
            int width = Math.Max(240, body.ClientSize.Width - body.Padding.Left - body.Padding.Right);
            int cursor = body.Padding.Top;
            int titleHeight = Math.Max(36, title.PreferredHeight);
            title.SetBounds(left, cursor, width, titleHeight);
            cursor = title.Bottom + 8;

            note.AutoSize = true;
            note.MinimumSize = new Size(width, 0);
            note.MaximumSize = new Size(width, 0);
            note.PerformLayout();
            var noteHeight = Math.Max(24, note.PreferredHeight);
            note.SetBounds(left, cursor, width, noteHeight);
            cursor = note.Bottom + 14;

            if (facts.Visible)
            {
                facts.SetBounds(left, cursor, width, Math.Max(96, facts.Height));
                LayoutFactsColumns(width);
                cursor = facts.Bottom + 12;
            }

            if (disks.Visible || refresh.Visible)
            {
                int refreshWidth = Math.Max(96, refresh.Width);
                int diskWidth = Math.Max(140, width - refreshWidth - 12);
                disks.SetBounds(left, cursor, diskWidth, Math.Max(28, disks.Height));
                refresh.SetBounds(left + diskWidth + 12, cursor - 2, refreshWidth, Math.Max(30, refresh.Height));
                cursor = Math.Max(disks.Bottom, refresh.Bottom) + 12;
            }

            if (bar.Visible)
            {
                bar.SetBounds(left, cursor, width, Math.Max(18, bar.Height));
                cursor = bar.Bottom + 12;
            }

            if (osPick.Visible)
            {
                osPick.SetBounds(left, cursor, Math.Min(width, Math.Max(300, osPick.PreferredSize.Width)), osPick.Height);
                cursor = osPick.Bottom + 8;
            }

            if (expDrivers.Visible)
            {
                expDrivers.AutoSize = false;
                int boxHeight = Math.Max(24, expDrivers.GetPreferredSize(new Size(width, 0)).Height);
                expDrivers.SetBounds(left, cursor, width, boxHeight);
                cursor = expDrivers.Bottom + 12;
            }

            int linksReserve = LinkHeight(ocLink, width) + LinkRowHeight(width, logLink, coffeeLink, creditsLink) +
                               LinkRowHeight(width, drvLink, appLink) + LinkHeight(doctorLink, width) +
                               LinkHeight(firmwareLink, width);

            if (guide.Visible)
            {
                guide.Left = left;
                guide.Top = cursor;
                guide.Width = width;
                guide.Height = Math.Max(180, body.ClientSize.Height - cursor - body.Padding.Bottom);
                body.AutoScrollMinSize = new Size(0, guide.Bottom + body.Padding.Bottom);
                return;
            }

            if (log.Visible)
            {
                log.Left = left;
                log.Top = cursor;
                log.Width = width;
                log.Height = Math.Max(120, body.ClientSize.Height - cursor - body.Padding.Bottom - linksReserve);
                cursor = log.Bottom + 12;
            }

            LayoutLink(ocLink, left, cursor, width, ref cursor);
            LayoutLinkRow(left, width, ref cursor, logLink, coffeeLink, creditsLink);
            LayoutLinkRow(left, width, ref cursor, drvLink, appLink);
            LayoutLink(doctorLink, left, cursor, width, ref cursor);
            LayoutLink(firmwareLink, left, cursor, width, ref cursor);
            body.AutoScrollMinSize = new Size(0, cursor + body.Padding.Bottom);
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
            MessageBox.Show(this, rc == 0 ? Loc.T("The NVIDIA driver is up to date.\r\n\r\n") + text + (dirs.Count > 1 ? "" : Loc.T("\r\n\r\nNo 1401 stick was plugged in; plug it in and run this again to update it too."))
                                          : Loc.T("The driver could not be updated:\r\n\r\n") + text, Loc.T("1401 - Update driver"));
        }

        // "Update 1401": the engine downloads the newest Windows app from the 1401 release, checks it against the release's
        // SHA256SUMS.txt and unpacks it; a small script then waits for this window to close, keeps a copy of the current
        // folder, mirrors the new files in (puts the copy back if that fails), and opens 1401 again. No reinstall.
        async void UpdateApp()
        {
            if (busy) return;
            busy = true; appLink.Enabled = false;
            string have = Application.ProductVersion.Split('+')[0];
            string work = Path.Combine(Engine.Work, "app-update");
            var lines = new List<string>();
            int rc = await Engine.Run("p1401.nullmoth appupdate " + Engine.Q(have) + " " + Engine.Q(work), l => { lock (lines) lines.Add(l); });
            busy = false; appLink.Enabled = true;
            string result = lines.LastOrDefault(l => l.StartsWith("RESULT ")) ?? "RESULT stop: the update check did not answer";
            if (result.StartsWith("RESULT uptodate"))
            { MessageBox.Show(this, "1401 " + have + " is the newest version.", "1401 - Update"); return; }
            if (rc != 0 || !result.StartsWith("RESULT ready "))
            { MessageBox.Show(this, "1401 could not update itself:\r\n\r\n" + result.Substring(7), "1401 - Update"); return; }
            var parts = result.Split(new[] { ' ' }, 4);
            string version = parts[2], src = parts[3], home = Engine.Home.TrimEnd('\\');
            if (!File.Exists(Path.Combine(src, "1401.exe"))) { MessageBox.Show(this, "The downloaded 1401 has no 1401.exe; nothing was changed.", "1401 - Update"); return; }
            if (MessageBox.Show(this, "1401 " + version + " is downloaded and checked. 1401 closes, updates itself and opens again.", "1401 - Update",
                                MessageBoxButtons.OKCancel) != DialogResult.OK) return;
            string backup = Path.Combine(work, "previous"), script = Path.Combine(work, "swap.cmd");
            // Only 1401's own files move: its top-level files are copied and its engine and NullMoth folders mirrored. A /MIR of
            // the whole folder would delete everything else in it when someone runs 1401 from Downloads or the Desktop.
            File.WriteAllText(script, string.Join("\r\n", new[] {
                "@echo off",
                ":wait",
                "tasklist /FI \"PID eq %1\" 2>nul | find \"%1\" >nul && (timeout /t 1 /nobreak >nul & goto wait)",
                "call :put \"%~3\" \"%~4\" || goto start",
                "call :put \"%~2\" \"%~3\" || call :put \"%~4\" \"%~3\"",
                ":start",
                "start \"\" \"%~3\\1401.exe\"",
                "exit /b 0",
                ":put",
                "robocopy \"%~1\" \"%~2\" 1401.exe 1401.exe.config README.txt LICENSE.txt BUILD-MANIFEST.json /R:2 /W:1 >nul",
                "if %ERRORLEVEL% GEQ 8 exit /b 1",
                "robocopy \"%~1\\engine\" \"%~2\\engine\" /MIR /R:2 /W:1 >nul",
                "if %ERRORLEVEL% GEQ 8 exit /b 1",
                "if exist \"%~1\\NullMoth\" robocopy \"%~1\\NullMoth\" \"%~2\\NullMoth\" /MIR /R:2 /W:1 >nul",
                "if %ERRORLEVEL% GEQ 8 exit /b 1",
                "exit /b 0",
                "" }));
            Process.Start(new ProcessStartInfo("cmd.exe", "/c \"\"" + script + "\" " + Process.GetCurrentProcess().Id + " \"" + src + "\" \"" + home + "\" \"" + backup + "\"\"")
            { CreateNoWindow = true, UseShellExecute = false, WorkingDirectory = work });
            Close();
        }

        void Say(string s)
        {
            if (InvokeRequired) { BeginInvoke(new Action<string>(Say), s); return; }
            if (s.StartsWith("PROGRESS ")) { int p; var parts = s.Split(' '); if (int.TryParse(parts[1], out p)) bar.Value = Math.Max(0, Math.Min(100, p)); return; }
            log.AppendText(s + Environment.NewLine);
        }

        void Show(params Control[] on)
        {
            foreach (Control c in new Control[] { facts, bar, log, disks, refresh, osPick, expDrivers, guide, ocLink, logLink }) c.Visible = on.Contains(c);
            drvLink.Visible = logLink.Visible;
            appLink.Visible = logLink.Visible;
            coffeeLink.Visible = logLink.Visible;
            creditsLink.Visible = logLink.Visible;
            doctorLink.Visible = logLink.Visible;
            firmwareLink.Visible = (page == 1 || page == 2) && firmwareGuideFile != null && File.Exists(firmwareGuideFile);
            firmwareLink.Enabled = !busy;
        }

        void Go(int p)
        {
            if (busy || p < 0 || p >= Steps.Length) return;
            page = p;
            body.AutoScrollPosition = Point.Empty;
            headTitle.Text = "1401 — " + Loc.T(Steps[p]);
            nav.Invalidate();
            for (int i = 0; i < Steps.Length; i++)
            {
                side[i].ForeColor = i == page ? Theme.Purple : (i < page ? Theme.Cyan : Theme.Muted);
                if (i == page)
                {
                    if (!side[i].Font.Bold)
                    {
                        var old = side[i].Font;
                        side[i].Font = new Font(old, FontStyle.Bold);
                        if (!ReferenceEquals(old, Theme.Body)) old.Dispose();
                    }
                }
                else if (side[i].Font.Bold)
                {
                    var old = side[i].Font;
                    side[i].Font = new Font(old, FontStyle.Regular);
                    if (!ReferenceEquals(old, Theme.Body)) old.Dispose();
                }
            }
            title.Text = Loc.T(Steps[page]); back.Enabled = page > 0 && page < Steps.Length - 1; next.Text = Loc.T("Continue >");
            switch (page)
            {
                case 0:
                    note.Text = Loc.T("The 1401 Assistant helps you install macOS on this PC, the way Boot Camp put Windows on a Mac.\r\n\r\n" +
                        "It checks this PC, builds the startup files macOS needs for your exact hardware, shows BIOS settings based on your scan and startup files, " +
                        "and makes a macOS install stick. Windows stays as it is. Nothing about this PC is sent anywhere.\r\n\r\n" +
                        "You need: an internet connection and a USB stick of 4 GB or more that can be erased.\r\n\r\n" +
                        "1401 is new and may not work on every PC. If it does not work on yours, set up OpenCore by hand with the guide below; " +
                        "the NullMoth app works on any OpenCore setup.");
                    Show(ocLink, logLink); var miss = Engine.Missing(); if (miss != null) { note.Text = miss; next.Enabled = false; } else next.Enabled = true;
                    break;
                case 1:
                    note.Text = Loc.T(scanned ? "This PC was checked. Continue, or check again." : "1401 reads this PC's hardware (processor, board, graphics, network, storage) and its ACPI tables. This takes about a minute.");
                    next.Text = Loc.T(scanned ? "Continue >" : "Check this PC"); Show(facts, log); next.Enabled = true; break;
                case 2:
                    note.Text = Loc.T(built ? summary.Split(new[] { "\r\n" }, StringSplitOptions.None)[0] : "Pick macOS 15 Sequoia or macOS 26 Tahoe below. 1401 builds the startup files (OpenCore EFI) for that version and checks them with OpenCore's own validator. Downloads OpenCore and drivers.");
                    next.Text = Loc.T(built ? "Continue >" : "Build"); Show(facts, log, osPick, expDrivers); next.Enabled = scanned;
                    if (built) { log.Text = summary; log.SelectionStart = 0; log.ScrollToCaret(); }
                    break;
                case 3:
                    if (showingPrerequisites)
                    {
                        title.Text = Loc.T("Firmware prerequisites");
                        note.Text = Loc.T("Review storage requirements before building. No EFI or firmware changes are made by this page. Return to the check or build when finished.");
                        Show(guide); next.Enabled = true; next.Text = Loc.T("Return >");
                        if (firmwareGuideFile != null && File.Exists(firmwareGuideFile)) guide.Navigate(firmwareGuideFile);
                    }
                    else
                    {
                        note.Text = Loc.T("These BIOS suggestions follow your scan and startup files. Check menu names in the exact board manual, then take a photo before restarting.");
                        Show(guide); next.Enabled = built;
                        if (guideFile != null && File.Exists(guideFile)) guide.Navigate(guideFile);
                    }
                    break;
                case 4:
                    note.Text = Loc.T("Plug in the USB stick that will become the macOS installer. EVERYTHING on it is erased.\r\n" +
                        "1401 downloads macOS from Apple onto it and adds the startup files") + Loc.T(summary.Contains("NVIDIA") ? " and the NullMoth NVIDIA driver." : ".");
                    next.Text = Loc.T(written ? "Continue >" : "Erase and create"); Show(disks, refresh, bar, log); next.Enabled = true; FillDisks(); break;
                case 5:
                    note.Text = Loc.T("The macOS stick is ready.\r\n\r\n1. Restart and open your board's boot menu (the key is in your BIOS steps), then choose the stick.\r\n" +
                        "2. In the 1401 boot menu choose \"Install macOS\" and follow Apple's installer. The screen can stay still for up to two minutes while macOS is read from the stick: do not restart.\r\n" +
                        "3. When macOS is running, open the NullMoth folder on the stick and run 1401.app to finish the NVIDIA driver.");
                    next.Text = Loc.T("Close"); Show(); next.Enabled = true; break;
            }
            LayoutBody(); LayoutFooter();
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
                else Say(Loc.T("Firmware review could not be generated. No EFI or firmware was changed. The build refusal still includes storage preparation guidance."));
            }
            catch (Exception) { Say(Loc.T("Firmware review is unavailable. No EFI or firmware was changed; use the storage guidance in the build refusal.")); }
            finally { busy = false; next.Enabled = true; }
        }

        // The companion file for this app's own version. A folder kept across updates holds every version, and the first
        // by name was used: a 1.8 app passed the 1.7 driver (10-10), and "1.10.0" sorts before "1.9.0". This version's
        // file first, then the highest version present.
        static string Companion(string prefix, string suffix)
        {
            if (!Directory.Exists(Engine.NullMothDir)) return null;
            var files = Directory.GetFiles(Engine.NullMothDir, prefix + "*" + suffix);
            var own = Application.ProductVersion.Split('+')[0];
            var exact = files.FirstOrDefault(f => string.Equals(Path.GetFileName(f), prefix + own + suffix, StringComparison.OrdinalIgnoreCase));
            if (exact != null) return exact;
            return files.OrderByDescending(f =>
            {
                var name = Path.GetFileName(f);
                Version v;
                return Version.TryParse(name.Substring(prefix.Length, Math.Max(0, name.Length - prefix.Length - suffix.Length)), out v) ? v : new Version(0, 0);
            }).FirstOrDefault();
        }

        // A stick's record of its last failed start: the newest opencore-*.txt, and the two newest panic-*.txt macOS saves
        // there (ApplePanic; a backtrace names the kext to switch off). bootfix.py reads them in the build.
        static List<string> StickBootLogs(IEnumerable<string> roots)
        {
            var files = new List<string>();
            foreach (var root in roots.Distinct(StringComparer.OrdinalIgnoreCase))
            {
                try
                {
                    // Send logs moves what it sent into NullMoth\sent-logs, so a build after sending found no log and the
                    // fix for the failure it recorded never ran (10-10: Zen 4/5 sticks still stopping at EB.MM.AKM). Both
                    // places count; OpenCore names its logs by date, so the newest name is the last start.
                    var dirs = new[] { root, Path.Combine(root, "NullMoth", "sent-logs") }.Where(Directory.Exists).ToList();
                    var newest = dirs.SelectMany(d => Directory.GetFiles(d, "opencore-*.txt"))
                                     .OrderByDescending(f => Path.GetFileName(f), StringComparer.OrdinalIgnoreCase).FirstOrDefault();
                    if (newest != null) files.Add(newest);
                    files.AddRange(dirs.SelectMany(d => Directory.GetFiles(d, "panic-*.txt"))
                                       .OrderByDescending(f => Path.GetFileName(f), StringComparer.OrdinalIgnoreCase).Take(2));
                }
                catch (Exception) { }
            }
            return files;
        }

        // Asks the 1401 release which version is newest. Offline or rate-limited ("unknown") never blocks anyone.
        async void CheckAppVersion()
        {
            string have = Application.ProductVersion.Split('+')[0];
            var lines = new List<string>();
            int rc = await Engine.Run("p1401.nullmoth appcheck " + Engine.Q(have), l => { lock (lines) lines.Add(l); });
            string result = lines.LastOrDefault(l => l.StartsWith("RESULT ")) ?? "";
            if (rc != 0 || !result.StartsWith("RESULT newer ")) return;
            mustUpdate = result.Substring("RESULT newer ".Length).Trim();
            AskToUpdate(have);
        }

        void AskToUpdate(string have)
        {
            if (MessageBox.Show(this, "This is 1401 " + have + ". 1401 " + mustUpdate + " is out, and it fixes problems that stop older " +
                                "versions. 1401 has to update before it builds or writes anything.\r\n\r\nUpdate now?",
                                "1401 - Update needed", MessageBoxButtons.OKCancel) == DialogResult.OK) UpdateApp();
        }

        async void OnNext()
        {
            if (busy) return;
            if (mustUpdate != null) { AskToUpdate(Application.ProductVersion.Split('+')[0]); return; }
            if (page == 3 && showingPrerequisites)
            {
                showingPrerequisites = false; Go(prerequisiteReturnPage); return;
            }
            if (page == 0) { Go(1); return; }
            // The PC restarted since Check this PC ran (a firmware change needs one): that report is history.
            bool rechecking = page == 1 && scanned && ScanEvidence.OlderThanThisBoot(scanDir);
            if (rechecking) scanned = built = false;
            if (page == 1 && !scanned)
            {
                if (SystemChecks.UnderWine()) { Say(Loc.T(SystemChecks.WineMessage)); return; }
                busy = true; next.Enabled = false; log.Clear();
                if (rechecking) Say(Loc.T("This PC restarted since it was checked; checking it again."));
                scanRunId = Guid.NewGuid().ToString("N");
                scanDir = ScanEvidence.RunDirectory(Engine.Work, scanRunId);
                ScanEvidence.Remember(Engine.Work, scanRunId);
                Say(Loc.T("Checking this PC..."));
                var scanLines = new List<string>();
                int rc = await Engine.Run("p1401.scan " + Engine.Q(scanDir) + " --run-id " + scanRunId, l => { scanLines.Add(l); Say(l); });
                ReportSaveStatus();
                busy = false; next.Enabled = true;
                if (rc != 0)
                {
                    Say(Loc.T("The check failed. The lines above say why."));
                    OfferOperationReport("check");
                    return;
                }
                scanned = true; LoadFacts(); await PrepareFirmwareGuide(); Say(Loc.T("Done.")); Go(1); return;
            }
            if (page == 2 && !built)
            {
                busy = true; next.Enabled = false; log.Clear();
                efiDir = Path.Combine(Engine.Work, "efi");
                var rep = Path.Combine(scanDir, "Report.json"); var acpi = Path.Combine(scanDir, "ACPI");
                var lines = new List<string>();
                Say(Loc.T("Building the startup files for this PC..."));
                // A stick that already failed to boot says why in its newest OpenCore log; the build reads it (bootfix.py).
                var roots = new List<string>(stickRoots);
                foreach (var d in DriveInfo.GetDrives())
                {
                    try { if (d.DriveType == DriveType.Removable && d.IsReady) roots.Add(d.RootDirectory.FullName); }
                    catch (Exception) { }
                }
                var logFiles = StickBootLogs(roots);
                buildLogFiles.Clear(); buildLogFiles.UnionWith(logFiles);
                var bootLogs = string.Concat(logFiles.Select(f => " --boot-log " + Engine.Q(f)));
                var stoppedFile = Path.Combine(Engine.Work, "stopped-at.txt");
                try { if (File.Exists(stoppedFile)) bootLogs += " --stopped-at " + Engine.Q(File.ReadAllText(stoppedFile).Trim()); } catch (Exception) { }
                if (bootLogs.Length > 0) Say(Loc.T("Using the last startup log on the stick to adjust this build."));
                int rc = await Engine.Run("p1401 build " + Engine.Q(rep) + " " + Engine.Q(acpi) + " " + Engine.Q(efiDir) + " --json --macos " + (osPick.SelectedIndex == 1 ? "25" : "24") + (expDrivers.Checked ? " --experimental-drivers" : "") + bootLogs, l => { lines.Add(l); });
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
                        Say(Loc.T("The build stopped: ") + (string.IsNullOrWhiteSpace(detail) ? Loc.F("Engine exit code {0}.", rc) : detail));
                        // the whole engine output, so a user can post it in a bug report
                        OfferOperationReport("build");
                        return;
                    }
                    var mv = "" + r["macos_version"]; macosFull = mv; darwin = mv.Split('.')[0];
                    var notices = r["notices"] as System.Collections.ArrayList;
                    // The notices that follow come from the engine in English and are shown verbatim: they name cards,
// chips and driver versions by their real identifiers, so translating them would misreport what the
// scan found. Only the sentence this app writes is localized.
                    summary = "macOS " + MacName(darwin) + Loc.T(" for this PC, as a ") + r["smbios"] + Loc.T(". The startup files passed OpenCore's own check.");
                    if (notices != null) foreach (var n in notices) if (IsSupportNotice("" + n)) summary += "\r\n" + n;
                    built = true; showingPrerequisites = false;
                }
                catch (Exception e) { Say(Loc.F("Could not read the build result ({0}). The saved operation report includes the engine output.", e.GetType().Name)); foreach (var l in lines.Take(40)) Say(l); OfferOperationReport("build"); return; }
                guideFile = Path.Combine(Engine.Work, "BIOS-steps.html");
                await Engine.Run("p1401.guide " + Engine.Q(rep) + " " + Engine.Q(Path.Combine(efiDir, "EFI", "OC", "config.plist")) + " --macos " + macosFull + " --html " + Engine.Q(guideFile), Say);
                ReportSaveStatus();
                Say("Done."); Go(2); return;
            }
            if (page == 4 && !built) { Go(2); return; }
            if (page == 4 && !written)
            {
                var d = disks.SelectedItem as UsbDisk;
                if (d == null) { MessageBox.Show(this, Loc.T("Plug in a USB stick and press Refresh."), "1401"); return; }
                // The build reads a failed start's log only from a stick that was plugged in while it ran. Most people
                // plug the stick in here, after the build, and erasing it deletes that log. WAS: AMD PCs that stopped in
                // boot.efi were rebuilt with the same settings every time, because their log never reached the build.
                var picked = d.Letters.Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries).Select(l => l + "\\").ToList();
                if (StickBootLogs(picked).Any(f => !buildLogFiles.Contains(f)))
                {
                    stickRoots.Clear(); stickRoots.AddRange(picked);
                    Say(Loc.T("This stick holds the log of a start that did not finish. Building again with it before the stick is erased."));
                    built = false; Go(2); OnNext(); return;
                }
                var ok = MessageBox.Show(this, Loc.F("Erase {0}", d) + Loc.F(" and make it the macOS installer?\r\n\r\nEverything on it will be lost."),
                    Loc.T("1401 - erase this stick?"), MessageBoxButtons.YesNo, MessageBoxIcon.Warning, MessageBoxDefaultButton.Button2);
                if (ok != DialogResult.Yes) return;
                busy = true; next.Enabled = false; refresh.Enabled = false; log.Clear(); bar.Value = 0;
                var args = "p1401.usbwriter write " + d.Number + " " + Engine.Q(efiDir) + " " + darwin;
                // the stick itself, not only its number: Windows can renumber it before or during the write
                args += " --stick-id " + Engine.Q(d.UniqueId) + " --stick-size " + d.Size + " --stick-name " + Engine.Q(d.Name);
                var pkg = Companion("nullmoth-nvidia-", ".tar.gz");
                if (pkg != null) args += " --driver " + Engine.Q(pkg);
                var mac = Companion("1401-Mac-", ".zip");
                if (mac != null) args += " --extra " + Engine.Q(mac);
                var report = Path.Combine(scanDir, "Report.json");
                if (File.Exists(report)) args += " --profile " + Engine.Q(report);
                if (d.Size > 256UL * 1024 * 1024 * 1024) args += " --allow-large";
                var writeLines = new List<string>();
                int rc = await Engine.Run(args, l => { writeLines.Add(l); Say(l); });
                // The stick holds a Mac or Windows partition (an older macOS installer, or a disk with a system on it).
                // Name what is there and ask once more; only an explicit Yes erases it.
                var found = writeLines.FirstOrDefault(l => l.Contains("1401-OS-PARTITIONS:"));
                if (rc != 0 && found != null)
                {
                    var what = found.Substring(found.IndexOf("1401-OS-PARTITIONS:") + 19).Trim();
                    var again = MessageBox.Show(this, "This stick is not empty: " + what + "\r\n\r\nThat is usually an old macOS installer, but it can also be a Mac backup or a Mac or Windows system. Erase it anyway?",
                        "1401 - erase what is on this stick?", MessageBoxButtons.YesNo, MessageBoxIcon.Warning, MessageBoxDefaultButton.Button2);
                    if (again == DialogResult.Yes) rc = await Engine.Run(args + " --erase-os-partitions", Say);
                }
                ReportSaveStatus();
                busy = false; next.Enabled = true; refresh.Enabled = true;
                // Windows renumbers USB sticks; a stale number in this list made every retry fail the same way (10-15).
                if (rc != 0 && writeLines.Any(l => l.Contains("1401-DISK-RENUMBERED"))) FillDisks();
                // The startup files came from an earlier check of this PC. Write was the only button left and every retry
                // stopped the same way: build again from the current check.
                if (rc != 0 && writeLines.Any(l => l.Contains("The scan changed after the EFI was built")))
                {
                    Say(Loc.T("The startup files were built from an earlier check of this PC. Building them again for this check."));
                    built = false; Go(2); OnNext(); return;
                }
                if (rc != 0) { Say(Loc.T("Writing the stick did not finish. The saved report includes the writer output; partial changes to the selected stick may remain.")); OfferOperationReport("write"); return; }
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
                if (mb != null) add(Loc.T("Board"), "" + mb["Name"]);
                var cpu = r.ContainsKey("CPU") ? r["CPU"] as Dictionary<string, object> : null;
                if (cpu != null) add(Loc.T("Processor"), "" + (cpu.ContainsKey("Processor Name") ? cpu["Processor Name"] : cpu["Manufacturer"]));
                var gpu = r.ContainsKey("GPU") ? r["GPU"] as Dictionary<string, object> : null;
                if (gpu != null) foreach (var g in gpu) add(Loc.T("Graphics"), g.Key);
                var net = r.ContainsKey("Network") ? r["Network"] as Dictionary<string, object> : null;
                if (net != null) foreach (var n in net) add(Loc.T("Network"), n.Key);
            }
            catch (Exception e) { Say(Loc.T("Could not read the report: ") + e.Message); }
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
            Say(Loc.T("Looking for USB sticks..."));
            var skipped = new List<string>(); List<UsbDisk> found = null; string err = null;
            var self = Self();
            var t = Task.Run(() => Disks.ListUsb(skipped));
            if (await Task.WhenAny(t, Task.Delay(30000)) != t)
                err = Loc.T("Windows did not answer the USB disk list within 30 seconds. Unplug card readers and other USB drives, then press Refresh.");
            else if (t.IsFaulted) err = Loc.T("Could not list USB sticks: ") + t.Exception.GetBaseException().Message;
            else found = t.Result;
            var why = new List<string>(t.IsCompleted && !t.IsFaulted ? skipped : new List<string>());
            foreach (var d in found ?? new List<UsbDisk>())
            {
                if (self.Length == 2 && d.Letters.ToUpperInvariant().Contains(self)) { why.Add(d + Loc.T(": 1401 is running from it")); continue; }
                if (d.Size < MinStick) { why.Add(d + Loc.T(": too small, 1401 needs 2 GB")); continue; }
                disks.Items.Add(d);
            }
            if (err != null) Say(err);
            if (disks.Items.Count > 0) { disks.SelectedIndex = 0; Say(Loc.F("Found {0} USB stick(s).", disks.Items.Count)); }
            else if (err == null)
            {
                Say(Loc.T("No USB stick found. Plug one in (4 GB or more, not the stick 1401 runs from) and press Refresh."));
                if (why.Count > 0) { Say(Loc.T("Disks 1401 saw and left out:")); foreach (var w in why) Say("  " + w); }
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
                Say(Engine.LastReport.Failure + Loc.T(" The operation output may remain visible, but a durable final report is unavailable."));
        }

        void OfferOperationReport(string kind)
        {
            var report = Engine.LastReport;
            if (report == null || !report.Saved)
            {
                Say(report == null ? Loc.T("The operation has no saved local report. The visible output remains available to copy.") : report.Failure);
                return;
            }
            Say(Loc.T("The local report is saved at ") + report.Path + Loc.T(". Scan for logs and send them can retry after restart."));
            OfferLog(report.Path, kind);
        }

        void OfferLog(string file, string kind)
        {
            var ask = MessageBox.Show(this,
                Loc.F("The {0} failed.\r\n\r\n1401 is sending this log to nullmothsystems.com so the bug can be found and fixed. " +
                "It holds this scan's hardware list, bounded device/CPU observations and what the check or build printed. Windows capabilities do not establish macOS support. Your Windows user name and PC name are removed first. " +
                "Nothing else on this PC is sent.\r\n\r\nClick OK to send it now, or Cancel to keep it only on this PC.", Loc.Op(kind)),
                Loc.T("1401 - sending the log"), MessageBoxButtons.OKCancel, MessageBoxIcon.Information, MessageBoxDefaultButton.Button1);
            if (ask != DialogResult.OK) { Say(Loc.T("The log was not sent. It stays in ") + file + Loc.T(".")); return; }
            var ids = new List<string>();
            var batch = NewBatch();
            var id = Send(file, "1401-" + kind + "-log.txt", kind + " failed", batch);
            if (id != null) ids.Add(id);
            var evidence = ScanEvidence.Find(Engine.Work, scanRunId, false);
            if (evidence != null) {
                var receipt = Send(evidence.Path, "1401-scan-evidence.json.txt", kind + " failed; saved evidence from this scan run; macOS support not assessed", batch);
                if (receipt != null) ids.Add(receipt);
            }
            Say(ids.Count > 0 ? Loc.T("Logs sent. Report IDs ") + string.Join(", ", ids) + Loc.T(" - mention them in the NullMoth Discord if you ask for help.")
                             : Loc.F("Could not send the logs ({0}). They stay on this PC.", lastSendError));
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
                   text.StartsWith("Graphics:", StringComparison.Ordinal) ||
                   text.StartsWith("Laptop display note:", StringComparison.Ordinal) ||
                   text.StartsWith("Intel I225-LM vP", StringComparison.Ordinal);
        }

        internal bool VerifySupportNoticePresentation()
        {
            // A fixture, not user text: it stands in for the notices the engine emits, in English, because
            // those name cards and chips by their real identifiers. It is asserted here rather than written
            // into summary, so the localized summary this app builds is never overwritten by the fixture.
            const string fixture = "Package verification\r\nLaptop display note: panel wiring requires verification.\r\nIntel I225-LM vP link testing is required.";
            built = scanned = true;
            Go(2);
            return log.Visible && log.Text == summary && log.ScrollBars == ScrollBars.Vertical &&
                   fixture.StartsWith("Package verification", StringComparison.Ordinal);
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
                    // The checks below compare against Loc.T, not a literal: the same build has to pass with the UI in
// English and in Chinese, and a literal here would report a false failure on one of them.
                    title.Text != Loc.T("Firmware prerequisites") || next.Text != Loc.T("Return >") || !guide.Visible || !next.Enabled || built) return false;
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
                if (next.Enabled || title.Text != Loc.T("Your BIOS steps") || built) return false;
                built = true; Go(3);
                if (!next.Enabled || next.Text != Loc.T("Continue >") || title.Text != Loc.T("Your BIOS steps")) return false;
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

        // People also boot EFIs they assembled themselves (or with other tools). The engine's efidoctor runs 1401's own
        // rules on that config: missing files, kext order, the NVIDIA driver's settings, the laptop GPU fix, and what the
        // stick's last failed boot log says. It shows what it would change and writes only after the user agrees, keeping
        // a backup of the old config next to it.
        async void CheckOwnEfi()
        {
            if (busy) return;
            string root;
            using (var pick = new FolderBrowserDialog { Description = Loc.T("Select the drive or folder that holds your EFI folder") })
            {
                if (pick.ShowDialog(this) != DialogResult.OK) return;
                root = pick.SelectedPath;
            }
            var args = "p1401.efidoctor " + Engine.Q(root);
            var rep = scanDir == null ? null : Path.Combine(scanDir, "Report.json");
            if (rep != null && File.Exists(rep)) args += " --report " + Engine.Q(rep);
            try
            {
                var newest = Directory.GetFiles(Path.GetPathRoot(root), "opencore-*.txt").OrderByDescending(f => f).FirstOrDefault();
                if (newest != null) args += " --boot-log " + Engine.Q(newest);
            }
            catch (Exception) { }
            busy = true;
            var lines = new List<string>();
            int rc = await Engine.Run(args, l => { lock (lines) lines.Add(l); });
            busy = false;
            var text = string.Join("\r\n", lines.Where(l => l.StartsWith("  ")));
            if (rc == 0) { MessageBox.Show(this, Loc.T("Your EFI passed every check 1401 makes.\r\n\r\n") + text, "1401", MessageBoxButtons.OK, MessageBoxIcon.Information); return; }
            bool fixable = lines.Any(l => l.StartsWith("  needs fixing"));
            if (!fixable) { MessageBox.Show(this, Loc.T("1401 found problems it cannot fix by itself:\r\n\r\n") + text, "1401", MessageBoxButtons.OK, MessageBoxIcon.Warning); return; }
            if (MessageBox.Show(this, text + Loc.T("\r\n\r\nFix these in your config.plist now? The current one is kept as a backup next to it."),
                                "1401", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return;
            busy = true; lines.Clear();
            rc = await Engine.Run(args + " --fix", l => { lock (lines) lines.Add(l); });
            busy = false;
            MessageBox.Show(this, string.Join("\r\n", lines.Where(l => l.StartsWith("  "))), "1401",
                            MessageBoxButtons.OK, rc == 0 ? MessageBoxIcon.Information : MessageBoxIcon.Warning);
        }

        internal void OfferStickLogs(bool asked)
        {
            if (IsDisposed || Disposing || !IsHandleCreated) return;
            var found = new List<string>();
            var configs = new List<string>();
            var provenance = new List<string>();   // "not built by 1401" / "edited after 1401 built it", per stick
            // asked from the link: the last failed build's log on this PC goes too
            {
                try { found.AddRange(DurableReport.Find(Engine.Work).Where(f => asked || Path.GetFileName(f).Contains("-crash-"))); }
                catch (Exception error) { Say(Loc.F("Saved reports could not be listed ({0}, code {1}). Check access to the app data folder; existing files were retained.", error.GetType().Name, error.HResult)); }
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
                    // 10-07: four stick logs ended at Apple's hand-off to the kernel and named no hardware
                    // or settings, so nothing in them could be fixed. The config that booted goes with them, serials removed.
                    var cfg = Path.Combine(d.RootDirectory.FullName, "EFI", "OC", "config.plist");
                    if (found.Any(f => Path.GetPathRoot(f) == d.RootDirectory.FullName) && File.Exists(cfg))
                    {
                        var safe = Path.Combine(Engine.Work, "stick-config-" + d.Name.TrimEnd('\\', ':') + ".txt");
                        File.WriteAllText(safe, RedactConfig(File.ReadAllText(cfg)));
                        configs.Add(safe);
                        var prov = StickProvenance(d.RootDirectory.FullName, cfg);
                        if (prov.Length > 0) provenance.Add(prov);
                    }
                }
                catch (Exception) { }
            }
            if (found.Count == 0)
            {
                if (asked) MessageBox.Show(this, Loc.T("No logs were found. Plug in the USB stick 1401 made (the one you started macOS from) and try again."),
                                           "1401", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }
            found = found.Where(f => DurableReport.IsLocal(Engine.Work, f)).Concat(configs).Concat(found.Where(f => !DurableReport.IsLocal(Engine.Work, f))).Distinct().Take(6).ToList();   // the site takes 30 uploads per hour from one address
            // 10-07: most sticks now reach the macOS kernel and then stop with nothing written (a hang leaves no panic
            // file), so the line the screen stopped on is the one fact the logs cannot hold. Optional; same two clicks.
            string screen;
            var ask = AskSend(
                Loc.F("1401 found {0} diagnostic file{1} (available scan/build evidence and startup logs from attached sticks).\r\n\r\n" +
                "These retain available failure and hardware observations. 1401 is sending them to nullmothsystems.com so the bug can be found and fixed. " +
                "They hold what OpenCore and macOS printed while starting, and the stick's OpenCore settings with serial numbers removed. " +
                "An included scan receipt records saved Windows hardware observations, even if the check failed; it does not prove this PC or the attached stick has that hardware. Nothing else on this PC is sent.\r\n\r\nClick Send to send them now, or Cancel to keep them locally.",
                found.Count, found.Count == 1 ? "" : Loc.T("s")),
                out screen);
            if (ask != DialogResult.OK) return;
            var what = "startup log from the stick" + (screen.Length > 0 ? "; screen stopped at: " + screen : "")
                       + (provenance.Count > 0 ? "; " + string.Join("; ", provenance) : "");
            // the dialog only for a foreign EFI: 1401 Mac setup itself edits the config it boots from, so "changed after"
            // is normal after a driver install and stays a note in the upload
            if (provenance.Any(x => x.Contains("not built by 1401")))
                MessageBox.Show(this, string.Join("\r\n\r\n", provenance.Where(x => x.Contains("not built by 1401"))) + "\r\n\r\nBuild the stick again with 1401: it makes the OpenCore settings this PC needs. "
                                + "A stick made elsewhere, or edited afterwards, cannot be fixed from its logs.", "1401", MessageBoxButtons.OK, MessageBoxIcon.Information);
            // 10-10: 13 stick logs stopped at EB.MM.AKM on sticks built before 1.10, whose build fixes those PCs; the users kept
            // starting the same stick. Say what fixes it, before the logs are moved.
            var akm = false;
            foreach (var f in found.Where(x => Path.GetFileName(x).StartsWith("opencore-", StringComparison.OrdinalIgnoreCase)))
            {
                try { if (File.ReadAllText(f).Contains("EB.MM.AKM")) akm = true; } catch (Exception) { }
            }
            if (akm)
                MessageBox.Show(this, "This stick stopped inside Apple's boot loader, before macOS started (EB.MM.AKM: no room in memory for the kernel).\r\n\r\n"
                                + "Starting the same stick again will stop the same way. Build it again with this 1401 with the stick plugged in: "
                                + "the build reads this log and changes the memory settings for this PC. Then write the stick and start from it.",
                                "1401", MessageBoxButtons.OK, MessageBoxIcon.Information);
            // the next build reads it too (bootfix.after_handoff): a hang after OpenCore leaves no file, only this line
            if (screen.Length > 0) { try { File.WriteAllText(Path.Combine(Engine.Work, "stopped-at.txt"), screen); } catch (Exception) { } }
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
            MessageBox.Show(this, ids.Count > 0 ? Loc.T("Sent ") + ids.Count + Loc.T(" log(s). Report ID ") + string.Join(", ", ids) + Loc.T(" - mention it in the NullMoth Discord if you ask for help.")
                                                : Loc.T("The logs could not be sent: ") + lastSendError + Loc.T("\r\nThey are still where they were; try again with Scan for logs and send them."),
                            "1401", MessageBoxButtons.OK, MessageBoxIcon.Information);
        }

        // The Mac identity OpenCore gives this PC (serial, board serial, UUID, ROM) is the only personal part of a config.
        // A stick log is only worth fixing when 1401 built the EFI that produced it. 10-10: a Ryzen 9 5900X stick hung at
        // AppleACPICPU running a hand-made EFI whose AMD patches all stop at macOS 10.15. 1401 writes NullMoth\system-profile.json
        // with the SHA-256 of every EFI file it built, so a missing profile means "not 1401's" and a changed config hash
        // means "edited after 1401 built it".
        static string StickProvenance(string root, string configPath)
        {
            try
            {
                var profile = Path.Combine(root, "NullMoth", "system-profile.json");
                if (!File.Exists(profile)) return "this stick's OpenCore EFI was not built by 1401";
                var text = File.ReadAllText(profile);
                var key = "\"OC/config.plist\":";
                var at = text.IndexOf(key, StringComparison.Ordinal);
                if (at < 0) return "";
                var q1 = text.IndexOf('"', at + key.Length);
                var q2 = q1 < 0 ? -1 : text.IndexOf('"', q1 + 1);
                if (q1 < 0 || q2 < 0) return "";
                var want = text.Substring(q1 + 1, q2 - q1 - 1);
                string have;
                using (var sha = System.Security.Cryptography.SHA256.Create())
                using (var fs = File.OpenRead(configPath))
                    have = BitConverter.ToString(sha.ComputeHash(fs)).Replace("-", "").ToLowerInvariant();
                return have == want ? "" : "this stick's OpenCore config was changed after 1401 built it";
            }
            catch (Exception) { return ""; }
        }

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
                                      Text = Loc.T("1401 - sending the startup logs"), FormBorderStyle = FormBorderStyle.FixedDialog,
                                      MaximizeBox = false, MinimizeBox = false, StartPosition = FormStartPosition.CenterParent,
                                      ClientSize = new Size(520, 380), Font = Theme.Body, AutoScroll = true })
            {
                f.SuspendLayout();
                const int margin = 14, contentWidth = 492;
                var msg = new Label { Text = text, Font = Theme.Body, AutoSize = true, MaximumSize = new Size(contentWidth, 0), Left = margin, Top = 12 };
                var q = new Label { Text = Loc.T("Optional: the last line on the screen when it stopped (for example \"PCI configuration begin\"):"),
                                    Font = Theme.Body, AutoSize = true, MaximumSize = new Size(contentWidth, 0), Left = margin };
                q.Top = msg.Bottom + 12;
                var box = new TextBox { Left = margin, Top = q.Bottom + 8, Width = contentWidth, MaxLength = 300 };
                var buttonTop = box.Bottom + 16;
                var send = new Button { Text = Loc.T("Send"), DialogResult = DialogResult.OK, Width = 84, Anchor = AnchorStyles.Bottom | AnchorStyles.Right };
                var cancel = new Button { Text = Loc.T("Cancel"), DialogResult = DialogResult.Cancel, Width = 84, Anchor = AnchorStyles.Bottom | AnchorStyles.Right };
                int requiredHeight = buttonTop + Math.Max(send.Height, cancel.Height) + 14;
                f.ClientSize = new Size(520, Math.Max(380, Math.Min(640, requiredHeight)));
                send.Left = f.ClientSize.Width - margin - send.Width - cancel.Width - 8; send.Top = f.ClientSize.Height - margin - send.Height;
                cancel.Left = f.ClientSize.Width - margin - cancel.Width; cancel.Top = send.Top;
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
