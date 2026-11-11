using System;
using System.Runtime.InteropServices;
using A1401;

/// <summary>Checks Argv.Quote against the parser Windows actually uses (CommandLineToArgvW), including the
/// trailing-backslash case that silently swallowed --stick-id and put the disk identity check out of reach.
/// Built and run by tests/test_windows_argv_quote.py with the .NET Framework compiler; no app is started.</summary>
static class ArgvQuoteCheck
{
    [DllImport("shell32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern IntPtr CommandLineToArgvW(string lpCmdLine, out int pNumArgs);

    [DllImport("kernel32.dll")]
    static extern IntPtr LocalFree(IntPtr hMem);

    static int failures;

    static void Exact(string input, string expected)
    {
        string got = Argv.Quote(input);
        if (got != expected)
        {
            Console.WriteLine("FAIL exact [" + input + "] got [" + got + "] want [" + expected + "]");
            failures++;
        }
    }

    static void RoundTrip(string input)
    {
        string command = "1401.exe " + Argv.Quote(input);
        int argc;
        IntPtr argv = CommandLineToArgvW(command, out argc);
        if (argv == IntPtr.Zero)
        {
            Console.WriteLine("FAIL parse [" + input + "] CommandLineToArgvW failed " + Marshal.GetLastWin32Error());
            failures++;
            return;
        }
        try
        {
            if (argc != 2)
            {
                Console.WriteLine("FAIL parse [" + input + "] argc=" + argc + " (the argument split apart)");
                failures++;
                return;
            }
            IntPtr one = Marshal.ReadIntPtr(argv, IntPtr.Size);
            string got = Marshal.PtrToStringUni(one);
            if (got != input)
            {
                Console.WriteLine("FAIL roundtrip [" + input + "] parsed [" + got + "]");
                failures++;
            }
        }
        finally
        {
            LocalFree(argv);
        }
    }

    static int Main()
    {
        Exact("plain", "plain");
        Exact("", "\"\"");
        Exact("D:\\", "D:\\");
        Exact("C:\\Program Files\\", "\"C:\\Program Files\\\\\"");
        Exact("a b", "\"a b\"");
        Exact("a\"b", "\"a\\\"b\"");

        RoundTrip("plain");
        RoundTrip("");
        RoundTrip("D:\\");
        RoundTrip("C:\\Users\\A B\\1401\\");
        RoundTrip("a b");
        RoundTrip("a\"b");
        RoundTrip("ends with two\\\\");
        RoundTrip("quote\" and \\ backslash");
        RoundTrip("C:\\Program Files\\1401\\recovery\\");

        if (failures == 0) Console.WriteLine("OK argv quoting");
        return failures == 0 ? 0 : 1;
    }
}
