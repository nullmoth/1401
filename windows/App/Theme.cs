using System;
using System.Drawing;
using System.IO;
using System.Windows.Forms;

namespace A1401
{
    /// <summary>The nullmothsystems.com look (site/www/assets/site.css): black and dark purple, Times New Roman
    /// headings, Courier New labels, Verdana body, bevelled purple buttons, and cyan meaning "it worked".
    /// Every face here ships with Windows, same rule as the site.</summary>
    static class Theme
    {
        static Color C(int rgb) { return Color.FromArgb((rgb >> 16) & 255, (rgb >> 8) & 255, rgb & 255); }

        static Color A(int a, int rgb) { return Color.FromArgb(a, C(rgb)); }

        // The palette in use; Use(light) swaps it. Dark is the site's; light is the same roles on lavender glass.
        // The site has no amber; a warning still has to read as one next to cyan and pink.
        public static Color Bg, Panel, Panel2, Line, Text, Muted, Purple, Purple2, Btn, BtnEdge, Cyan, Err, Amber, LogBg;
        public static Color DeskBg, Neb1, Neb2, Neb3, StripeA, StripeB, Well2, GoA, GoB, GoText, BtnA, BtnB, BtnText, GlassTint, BarTint;
        public static Color[] Stars;
        static Theme() { Use(false); }

        public static void Use(bool light)
        {
            if (!light)
            {
                Bg = C(0x000000); Panel = C(0x0b0613); Panel2 = C(0x150a24); Line = C(0x3b1f5f); Text = C(0xe6ddf3); Muted = C(0xa898c2);
                Purple = C(0xb98aff); Purple2 = C(0x7c3fd0); Btn = C(0x4b1f86); BtnEdge = C(0xa77ae6); Cyan = C(0x58e6ea); Err = C(0xff7092);
                Amber = C(0xffcf70); LogBg = C(0x000001);
                DeskBg = C(0x000000); Neb1 = A(150, 0x7c3fd0); Neb2 = A(76, 0x58e6ea); Neb3 = A(82, 0xe59bff);
                StripeA = A(82, 0xb98aff); StripeB = A(90, 0x0b0613); Well2 = A(140, 0x000000);
                GoA = C(0xd4b4ff); GoB = C(0x9a63f0); GoText = C(0x0b0613); BtnA = A(230, 0x5c28a3); BtnB = A(230, 0x2a1150); BtnText = Color.White;
                GlassTint = A(150, 0x150a24); BarTint = A(120, 0x0b0613);
                Stars = new[] { C(0xcdb6ff), C(0xffffff), C(0xd9c8ff), C(0x8e6ad0), C(0xb89cff), C(0x58e6ea) };
            }
            else
            {
                Bg = C(0xf6f1fd); Panel = C(0xece3fa); Panel2 = C(0xe4d8f7); Line = C(0xc9b6ea); Text = C(0x1a0d2e); Muted = C(0x56466f);
                Purple = C(0x6a2fc0); Purple2 = C(0x9a63f0); Btn = C(0xe2d6f7); BtnEdge = C(0x7c3fd0); Cyan = C(0x0b6b70); Err = C(0xb0003a);
                Amber = C(0x7a4f00); LogBg = C(0xfffffe);
                DeskBg = C(0xefe8fb); Neb1 = A(140, 0xb98aff); Neb2 = A(102, 0x58e6ea); Neb3 = A(115, 0xe59bff);
                StripeA = A(216, 0xffffff); StripeB = A(76, 0xb98aff); Well2 = A(224, 0xffffff);
                GoA = C(0x9a63f0); GoB = C(0x6a2fc0); GoText = Color.White; BtnA = A(242, 0xffffff); BtnB = A(242, 0xe2d6f7); BtnText = C(0x2a1150);
                GlassTint = A(150, 0xffffff); BarTint = A(110, 0xffffff);
                Stars = new[] { C(0x9a63f0), C(0x7c3fd0), C(0xb98aff), C(0x6a2fc0), C(0x9a63f0), C(0x2f9a9f) };
            }
        }

        /// <summary>Each role's colour in one palette mapped to the same role in the other, by ARGB, for recolouring the
        /// controls that were built with the old palette. Roles that share a colour (Bg and DeskBg) keep the first.</summary>
        public static System.Collections.Generic.Dictionary<int, Color> Mapping(bool fromLight, bool toLight)
        {
            Use(fromLight);
            var from = new[] { Bg, Panel, Panel2, Line, Text, Muted, Purple, Purple2, Btn, BtnEdge, Cyan, Err, Amber, LogBg };
            Use(toLight);
            var to = new[] { Bg, Panel, Panel2, Line, Text, Muted, Purple, Purple2, Btn, BtnEdge, Cyan, Err, Amber, LogBg };
            var map = new System.Collections.Generic.Dictionary<int, Color>();
            for (int i = 0; i < from.Length; i++) if (!map.ContainsKey(from[i].ToArgb())) map[from[i].ToArgb()] = to[i];
            return map;
        }

        // Every face here ships with Windows, same rule as the site. The Chinese UI needs a face that
        // actually carries CJK glyphs: Verdana, Times New Roman and Courier New do not, so Windows
        // would fall back per-character and the sizes would not match. Microsoft YaHei ships with
        // every supported Windows and covers Latin and Han in one face.
        internal static string Face(string latin) { return Loc.Language == "zh" ? "Microsoft YaHei UI" : latin; }

        public static readonly Font Body = new Font(Face("Verdana"), 9.75f);
        public static readonly Font Title = new Font(Face("Times New Roman"), 20f, FontStyle.Bold);
        public static readonly Font Brand = new Font(Face("Times New Roman"), 22f, FontStyle.Bold);
        public static readonly Font Mono = new Font(Face("Courier New"), 10f, FontStyle.Bold);
        public static readonly Font Link = new Font(Face("Verdana"), 9.5f);
        public static readonly Font Log = new Font(Face("Courier New"), 9f);
        public static readonly Font Fact = new Font(Face("Courier New"), 9.5f);
        public static readonly Font Picker = new Font(Face("Courier New"), 10f);

        /// <summary>The site's bevelled button: purple face, light edge, brighter on hover.</summary>
        public static void Style(Button b, bool primary = true)
        {
            b.FlatStyle = FlatStyle.Flat;
            b.UseVisualStyleBackColor = false;
            b.BackColor = primary ? Btn : Panel2;
            b.ForeColor = Color.White;
            b.FlatAppearance.BorderSize = 0;
            b.Cursor = Cursors.Hand;
            // drawn as a rounded glass button (Glass.PaintButton); Tag says which of the two looks
            b.Tag = primary ? "primary" : null;
            b.Paint -= Glass.PaintButton; b.Paint += Glass.PaintButton;
        }

        public static void Style(ListBox l)
        {
            l.BackColor = Bg;
            l.ForeColor = Text;
            l.BorderStyle = BorderStyle.FixedSingle;
            l.Font = new Font(Loc.Language == "zh" ? "Microsoft YaHei UI" : "Courier New", 10f);
        }

        /// <summary>The moth mark from the site, embedded in the exe. Null if it is somehow missing; the header
        /// then shows the name alone rather than failing to open.</summary>
        public static Image Mark()
        {
            using (var s = typeof(Theme).Assembly.GetManifestResourceStream("moth-mark.jpg"))
                return s == null ? null : Image.FromStream(new MemoryStream(ReadAll(s)));
        }

        static byte[] ReadAll(Stream s)
        {
            using (var m = new MemoryStream()) { s.CopyTo(m); return m.ToArray(); }
        }
    }

    /// <summary>What the tester was asked to change, so "Find my report" can walk them back: Secure Boot (they turn it
    /// off by hand) and BitLocker (paused by this app). Kept in HKLM; the uninstaller removes it.
    /// The reminders do not depend on these marks: the report page always reads the live Secure Boot and BitLocker
    /// state and says what it sees. A mark only sharpens the wording ("it was on before you scanned").</summary>
    static class Restore
    {
        // These marks used to be files under C:\ProgramData\NullMoth\1401 Probe. Any standard user may create folders in ProgramData, and
        // one made before this app ran is theirs (CREATOR OWNER, full control): they could aim it anywhere with a link,
        // and this app writes and deletes there as admin. Standard users cannot create keys under HKLM\SOFTWARE, so a
        // mark here was written by an admin. Registry64 explicitly, so the path matches the uninstaller's SetRegView 64.
        const string KeyPath = @"SOFTWARE\NullMoth\1401 Probe";

        static Microsoft.Win32.RegistryKey Hklm()
        {
            return Microsoft.Win32.RegistryKey.OpenBaseKey(Microsoft.Win32.RegistryHive.LocalMachine, Microsoft.Win32.RegistryView.Registry64);
        }

        public static string Mark(string what)
        {
            try
            {
                using (var hklm = Hklm())
                using (var k = hklm.CreateSubKey(KeyPath))
                    k.SetValue(what, DateTime.UtcNow.ToString("o"));
                return null;
            }
            catch (Exception e) { return e.Message; }  // the reason goes back to the caller
        }

        public static bool Has(string what)
        {
            try
            {
                using (var hklm = Hklm())
                using (var k = hklm.OpenSubKey(KeyPath))
                    return k != null && k.GetValue(what) != null;
            }
            catch (Exception) { return false; }  // no mark readable = plain wording; the live state is still shown
        }

        public static void Clear(string what)
        {
            try
            {
                using (var hklm = Hklm())
                using (var k = hklm.OpenSubKey(KeyPath, true))
                    if (k != null) k.DeleteValue(what, false);
            }
            catch (Exception) { }  // a mark that outlives its reason only makes a reminder more insistent
        }
    }
}
