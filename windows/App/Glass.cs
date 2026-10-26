using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Windows.Forms;

namespace A1401
{
    /// <summary>The NullMoth glass look: the site's drifting starfield painted by the form, see-through panels over it,
    /// rounded buttons, and a light/dark switch. The palette lives in Theme; Glass swaps it and repaints.</summary>
    static class Glass
    {
        // The site's sky: three layers of stars on their own tiles, each drifting two tiles across and one down per loop
        // (so the loop has no seam), at different speeds. Positions are the site's (next.css), scaled to whole tiles.
        struct Star { public float X, Y, R; public int Tone; }
        static readonly int[] Tiles = { 240, 180, 300 };
        static readonly float[] LoopSeconds = { 130f, 185f, 250f };
        static readonly Star[][] Layers =
        {
            new[] { S(23, 41, 1.5f, 0), S(157, 12, 1.5f, 1), S(201, 187, 2f, 2), S(96, 118, 1.5f, 1), S(188, 74, 1.5f, 4), S(52, 205, 1.5f, 3) },
            new[] { S(91, 133, 1.5f, 3), S(37, 97, 1.5f, 1), S(131, 21, 1.5f, 4), S(158, 162, 1.5f, 0), S(12, 54, 1.5f, 2) },
            new[] { S(61, 211, 2.5f, 1), S(251, 71, 2f, 5), S(171, 143, 1.5f, 0), S(218, 262, 1.5f, 4), S(114, 28, 1.5f, 1), S(284, 190, 2f, 2) },
        };
        static Star S(float x, float y, float r, int tone) { return new Star { X = x, Y = y, R = r, Tone = tone }; }

        static readonly DateTime Start = DateTime.UtcNow;
        public static bool Light { get; private set; }

        static readonly string PrefFile = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "NullMoth", "1401", "theme.txt");

        public static void LoadPreference()
        {
            try { Light = File.Exists(PrefFile) && File.ReadAllText(PrefFile).Trim() == "light"; }
            catch (Exception) { Light = false; }   // an unreadable choice means the default, dark
        }

        static void SavePreference()
        {
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(PrefFile));
                File.WriteAllText(PrefFile, Light ? "light" : "dark");
            }
            catch (Exception) { }   // the switch still works for this session
        }

        /// <summary>Paints the desk: the background colour, three soft nebula glows, then the drifting stars.</summary>
        public static void PaintSky(Graphics g, Rectangle r)
        {
            g.Clear(Theme.DeskBg);
            g.SmoothingMode = SmoothingMode.AntiAlias;
            Glow(g, r, 0.14f, 0.20f, 0.40f, Theme.Neb1);
            Glow(g, r, 0.86f, 0.82f, 0.38f, Theme.Neb2);
            Glow(g, r, 0.68f, 0.06f, 0.34f, Theme.Neb3);
            double t = (DateTime.UtcNow - Start).TotalSeconds;
            for (int layer = 0; layer < Layers.Length; layer++)
            {
                int tile = Tiles[layer];
                double f = (t % LoopSeconds[layer]) / LoopSeconds[layer];
                float dx = (float)(-2 * tile * f), dy = (float)(tile * f);
                // a slow twinkle per layer, as the site's opacity animation
                int alpha = (int)(170 + 85 * Math.Cos(t * 2 * Math.PI / (5 + layer * 3)));
                foreach (var s in Layers[layer])
                {
                    var c = Color.FromArgb(alpha, Theme.Stars[s.Tone]);
                    using (var b = new SolidBrush(c))
                        for (float x = Mod(s.X + dx, tile) - tile; x < r.Width + tile; x += tile)
                            for (float y = Mod(s.Y + dy, tile) - tile; y < r.Height + tile; y += tile)
                                g.FillEllipse(b, r.X + x - s.R, r.Y + y - s.R, s.R * 2, s.R * 2);
                }
            }
        }

        static float Mod(float a, float m) { float v = a % m; return v < 0 ? v + m : v; }

        static void Glow(Graphics g, Rectangle r, float cx, float cy, float radius, Color c)
        {
            float rad = Math.Max(r.Width, r.Height) * radius;
            var rect = new RectangleF(r.X + r.Width * cx - rad, r.Y + r.Height * cy - rad, rad * 2, rad * 2);
            using (var path = new GraphicsPath())
            {
                path.AddEllipse(rect);
                using (var b = new PathGradientBrush(path) { CenterColor = c, SurroundColors = new[] { Color.FromArgb(0, c) } })
                    g.FillEllipse(b, rect);
            }
        }

        public static GraphicsPath Round(RectangleF r, float radius)
        {
            var p = new GraphicsPath();
            float d = Math.Min(radius * 2, Math.Min(r.Width, r.Height));
            if (d <= 0) { p.AddRectangle(r); return p; }
            p.AddArc(r.X, r.Y, d, d, 180, 90);
            p.AddArc(r.Right - d, r.Y, d, d, 270, 90);
            p.AddArc(r.Right - d, r.Bottom - d, d, d, 0, 90);
            p.AddArc(r.X, r.Bottom - d, d, d, 90, 90);
            p.CloseFigure();
            return p;
        }

        /// <summary>A rounded glass button: gradient fill, light top edge, dark bottom edge; primary is the bright one.</summary>
        public static void PaintButton(object sender, PaintEventArgs e)
        {
            var b = (Button)sender;
            bool primary = (b.Tag as string) == "primary";
            var g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            PaintBehind(b, g);
            var r = new RectangleF(1, 1, b.Width - 3, b.Height - 4);
            Color top = primary ? Theme.GoA : Theme.BtnA, bottom = primary ? Theme.GoB : Theme.BtnB;
            if (!b.Enabled) { top = Color.FromArgb(110, top); bottom = Color.FromArgb(110, bottom); }
            using (var path = Round(r, 9))
            {
                using (var shadow = Round(new RectangleF(r.X, r.Y + 2, r.Width, r.Height), 9))
                using (var sb = new SolidBrush(Color.FromArgb(90, 0, 0, 0))) g.FillPath(sb, shadow);
                using (var fill = new LinearGradientBrush(r, top, bottom, LinearGradientMode.Vertical)) g.FillPath(fill, path);
                using (var edge = new Pen(Theme.Line, 1f)) g.DrawPath(edge, path);
            }
            var fg = primary ? Theme.GoText : Theme.BtnText;
            if (!b.Enabled) fg = Color.FromArgb(140, fg);
            TextRenderer.DrawText(g, b.Text, b.Font, Rectangle.Round(r), fg,
                TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter | TextFormatFlags.EndEllipsis);
        }

        /// <summary>What shows around a rounded control: the sky at its place on the form, then its panel's glass tint;
        /// on a plain parent, the parent's colour.</summary>
        public static void PaintBehind(Control c, Graphics g)
        {
            var panel = c.Parent as GlassPanel;
            var form = c.FindForm();
            if (panel == null || form == null)
            {
                using (var bg = new SolidBrush(c.Parent != null ? c.Parent.BackColor : Theme.DeskBg)) g.FillRectangle(bg, c.ClientRectangle);
                return;
            }
            var origin = form.PointToClient(c.PointToScreen(Point.Empty));
            var state = g.Save();
            g.TranslateTransform(-origin.X, -origin.Y);
            PaintSky(g, form.ClientRectangle);
            g.Restore(state);
            var tint = panel.Tint();
            if (tint.A > 0) using (var b = new SolidBrush(tint)) g.FillRectangle(b, c.ClientRectangle);
        }

        /// <summary>Swaps the palette and recolours every control under root: each colour that was a dark-palette colour
        /// becomes the same role's light one (and back), so no control needs to know its role.</summary>
        public static void SetLight(Control root, bool light)
        {
            if (light == Light) return;
            var map = Theme.Mapping(Light, light);
            Light = light;
            Theme.Use(light);
            Recolour(root, map);
            SavePreference();
            root.Invalidate(true);
        }

        public static void ApplyLoaded(Control root)
        {
            if (!Light) return;
            Light = false;
            SetLight(root, true);
        }

        static void Recolour(Control c, Dictionary<int, Color> map)
        {
            Color v;
            if (c.BackColor != Color.Transparent && map.TryGetValue(c.BackColor.ToArgb(), out v)) c.BackColor = v;
            if (map.TryGetValue(c.ForeColor.ToArgb(), out v)) c.ForeColor = v;
            var link = c as LinkLabel;
            if (link != null && map.TryGetValue(link.LinkColor.ToArgb(), out v)) link.LinkColor = v;
            foreach (Control child in c.Controls) Recolour(child, map);
        }
    }

    /// <summary>A panel the sky shows through: it paints its stretch of the form's sky, then its glass tint over it.
    /// Double-buffered, so the drifting stars do not flicker the text on it.</summary>
    class GlassPanel : Panel
    {
        public Func<Color> Tint = () => Color.Transparent;
        public bool Stripes;
        public GlassPanel()
        {
            SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.UserPaint
                     | ControlStyles.ResizeRedraw | ControlStyles.SupportsTransparentBackColor, true);
        }

        protected override void OnPaintBackground(PaintEventArgs e)
        {
            var form = FindForm();
            var origin = form == null ? Point.Empty : form.PointToClient(PointToScreen(Point.Empty));
            var state = e.Graphics.Save();
            e.Graphics.TranslateTransform(-origin.X, -origin.Y);
            Glass.PaintSky(e.Graphics, form == null ? ClientRectangle : form.ClientRectangle);
            e.Graphics.Restore(state);
            var tint = Tint();
            if (tint.A > 0) using (var b = new SolidBrush(tint)) e.Graphics.FillRectangle(b, ClientRectangle);
            if (Stripes)
                using (var a = new Pen(Theme.StripeA)) using (var c = new Pen(Theme.StripeB))
                    for (int y = 0; y < Height; y += 2) { e.Graphics.DrawLine(a, 0, y, Width, y); e.Graphics.DrawLine(c, 0, y + 1, Width, y + 1); }
            using (var edge = new Pen(Theme.Line)) e.Graphics.DrawLine(edge, 0, Height - 1, Width, Height - 1);
        }
    }

    /// <summary>The light/dark switch in the title bar: a pill with a moon and a sun and a knob that slides.</summary>
    class ThemeSwitch : Control
    {
        public event EventHandler Toggled;
        public ThemeSwitch()
        {
            SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.UserPaint
                     | ControlStyles.SupportsTransparentBackColor, true);
            BackColor = Color.Transparent; Size = new Size(48, 24); Cursor = Cursors.Hand;
            AccessibleName = "Switch between light and dark"; AccessibleRole = AccessibleRole.CheckButton;
        }

        protected override void OnClick(EventArgs e) { base.OnClick(e); if (Toggled != null) Toggled(this, e); }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics; g.SmoothingMode = SmoothingMode.AntiAlias;
            var r = new RectangleF(0.5f, 0.5f, Width - 1.5f, Height - 1.5f);
            using (var p = Glass.Round(r, r.Height / 2))
            {
                using (var b = new SolidBrush(Theme.Well2)) g.FillPath(b, p);
                using (var pen = new Pen(Theme.Line)) g.DrawPath(pen, p);
            }
            using (var m = new SolidBrush(Theme.Muted))
            {
                g.FillEllipse(m, 6, Height / 2f - 4, 8, 8);                    // moon
                using (var cut = new SolidBrush(Theme.Well2)) g.FillEllipse(cut, 9, Height / 2f - 6, 8, 8);
                g.FillEllipse(m, Width - 15, Height / 2f - 3.5f, 7, 7);        // sun
            }
            float kx = Glass.Light ? Width - Height + 1 : 2;
            var knob = new RectangleF(kx, 2, Height - 5, Height - 5);
            using (var kb = new LinearGradientBrush(knob, Theme.GoA, Theme.GoB, LinearGradientMode.Vertical)) g.FillEllipse(kb, knob);
        }
    }
}
