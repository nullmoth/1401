using System.Text;

namespace A1401
{
    /// <summary>One argument, quoted for the Windows command line exactly as CommandLineToArgvW parses it.
    /// Engine.Run concatenates its arguments into one string, so a trailing backslash (a folder path such as D:\)
    /// must not escape the closing quote: that turned "--stick-id ..." into part of the previous argument and the
    /// writer then had no identity to check the disk against.</summary>
    static class Argv
    {
        public static string Quote(string value)
        {
            if (value == null) value = "";
            bool special = false;
            foreach (char c in value)
            {
                if (c == ' ' || c == '\t' || c == '\n' || c == '\v' || c == '"') { special = true; break; }
            }
            if (value.Length > 0 && !special) return value;
            var sb = new StringBuilder();
            sb.Append('"');
            int backslashes = 0;
            foreach (char c in value)
            {
                if (c == '\\') { backslashes++; continue; }
                if (c == '"')
                {
                    // backslashes before an embedded quote are doubled, then the quote is escaped
                    sb.Append('\\', backslashes * 2 + 1);
                    sb.Append('"');
                    backslashes = 0;
                }
                else
                {
                    sb.Append('\\', backslashes);
                    sb.Append(c);
                    backslashes = 0;
                }
            }
            // backslashes before the closing quote are doubled, so the closing quote stays a quote
            sb.Append('\\', backslashes * 2);
            sb.Append('"');
            return sb.ToString();
        }
    }
}
