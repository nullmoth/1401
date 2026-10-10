using System;
using System.Collections.Generic;
using System.Globalization;

namespace A1401
{
    /// <summary>UI text. The English string is the key, so a missing translation falls back to the
    /// original wording instead of an empty label. Selection follows the Windows display language;
    /// A1401_LANG overrides it, which is what the packaged verification session uses to check both
    /// languages from one build.</summary>
    static class Loc
    {
        static readonly Dictionary<string, string> Zh = new Dictionary<string, string>
        {
            // --- window chrome, brand line, navigation steps ---
            { "1401 Assistant", "1401 助手" },
            { "1401 Assistant  -  macOS on the PC you already own", "1401 助手  -  在你自己的电脑上装 macOS" },
            { "Introduction", "简介" },
            { "Check this PC", "检测本机" },
            { "Build the Mac setup", "构建 Mac 启动环境" },
            { "Your BIOS steps", "你的 BIOS 设置步骤" },
            { "Create the macOS stick", "制作 macOS 启动盘" },
            { "Done", "完成" },

            // --- navigation and buttons ---
            { "< Back", "< 返回" },
            { "Continue >", "继续 >" },
            { "Refresh", "刷新" },
            { "Return >", "返回 >" },
            { "Close", "关闭" },
            { "Build", "构建" },
            { "Erase and create", "擦除并创建" },

            // --- links on the introduction page ---
            { "OpenCore Install Guide (dortania.github.io/OpenCore-Install-Guide)", "OpenCore 安装指南 (dortania.github.io/OpenCore-Install-Guide)" },
            { "Something went wrong? Scan for logs and send them", "出问题了？扫描日志并发送" },
            { "Update the NVIDIA driver (newest release, here and on your 1401 stick)", "更新 NVIDIA 驱动（最新版本，同时更新此处和你的 1401 启动盘）" },
            { "Built your own EFI? Check it (and fix it) with the same rules 1401 uses", "自己搭过 EFI？用 1401 相同的规则检查（并修复）" },
            { "Review firmware prerequisites", "查看固件前置条件" },

            // --- introduction ---
            { "The 1401 Assistant helps you install macOS on this PC, the way Boot Camp put Windows on a Mac.\r\n\r\n" +
              "It checks this PC, builds the startup files macOS needs for your exact hardware, shows BIOS settings based on your scan and startup files, " +
              "and makes a macOS install stick. Windows stays as it is. Nothing about this PC is sent anywhere.\r\n\r\n" +
              "You need: an internet connection and a USB stick of 4 GB or more that can be erased.\r\n\r\n" +
              "1401 is new and may not work on every PC. If it does not work on yours, set up OpenCore by hand with the guide below; " +
              "the NullMoth app works on any OpenCore setup.",
              "1401 助手帮你在本机安装 macOS，就像 Boot Camp 把 Windows 装到 Mac 上那样。\r\n\r\n" +
              "它会检测本机，为你的具体硬件构建 macOS 所需的启动文件，根据扫描结果和启动文件给出 BIOS 设置，并制作 macOS 安装盘。Windows 保持原样。本机的任何信息都不会被发送出去。\r\n\r\n" +
              "你需要：一台能上网的电脑，以及一块 4 GB 以上、可以被清空的 U 盘。\r\n\r\n" +
              "1401 是新项目，不保证在每台机器上都能用。如果你的机器不行，可以按下面的指南手动配置 OpenCore；NullMoth 应用在任何 OpenCore 环境下都能工作。" },

            // --- step: check this PC ---
            { "This PC was checked. Continue, or check again.", "本机已检测完毕。可以继续，也可以重新检测。" },
            { "1401 reads this PC's hardware (processor, board, graphics, network, storage) and its ACPI tables. This takes about a minute.",
              "1401 会读取本机的硬件信息（处理器、主板、显卡、网络、存储）以及 ACPI 表。大约需要一分钟。" },

            // --- step: build ---
            { "1401 now picks the newest macOS your hardware runs and builds the startup files (OpenCore EFI) for it, then checks them with OpenCore's own validator. Downloads OpenCore and drivers.",
              "1401 现在会挑选你的硬件能运行的最新 macOS 版本，为它构建启动文件（OpenCore EFI），然后用 OpenCore 自带的校验器检查。需要下载 OpenCore 和驱动。" },
            { " for this PC, as a ", "，为本机生成的机型为 " },
            { ". The startup files passed OpenCore's own check.", "。启动文件已通过 OpenCore 自带的检查。" },

            // --- step: BIOS ---
            { "Firmware prerequisites", "固件前置条件" },
            { "Review storage requirements before building. No EFI or firmware changes are made by this page. Return to the check or build when finished.",
              "在构建前查看存储要求。本页面不会生成 EFI，也不会改动固件。看完后返回检测或构建步骤。" },
            { "These BIOS suggestions follow your scan and startup files. Check menu names in the exact board manual, then take a photo before restarting.",
              "这些 BIOS 建议来自你的扫描结果和启动文件。请对照主板的确切说明书核对菜单名称，重启前先拍照留存。" },

            // --- step: create the stick ---
            { "Plug in the USB stick that will become the macOS installer. EVERYTHING on it is erased.\r\n" +
              "1401 downloads macOS from Apple onto it and adds the startup files",
              "插入将要变成 macOS 安装盘的 U 盘。盘上的所有内容都会被清空。\r\n" +
              "1401 会从 Apple 下载 macOS 写入该盘，并加入启动文件" },
            { " and the NullMoth NVIDIA driver.", " 以及 NullMoth NVIDIA 驱动。" },

            // --- step: done ---
            { "The macOS stick is ready.\r\n\r\n1. Restart and open your board's boot menu (the key is in your BIOS steps), then choose the stick.\r\n" +
              "2. In the 1401 boot menu choose \"Install macOS\" and follow Apple's installer.\r\n" +
              "3. When macOS is running, open the NullMoth folder on the stick and run 1401.app to finish the NVIDIA driver.",
              "macOS 启动盘已就绪。\r\n\r\n1. 重启并打开主板的启动菜单（按键见 BIOS 设置步骤），然后选择该 U 盘。\r\n" +
              "2. 在 1401 启动菜单中选择 \"Install macOS\"，按 Apple 安装程序的提示操作。\r\n" +
              "3. macOS 启动后，打开 U 盘上的 NullMoth 文件夹，运行 1401.app 完成 NVIDIA 驱动的安装。" },

            // --- progress and log lines ---
            { "Checking this PC...", "正在检测本机..." },
            { "Building the startup files for this PC...", "正在为本机构建启动文件..." },
            { "Looking for USB sticks...", "正在查找 U 盘..." },
            { "Done.", "完成。" },
            { "The check failed. The lines above say why.", "检测失败。上面的日志说明了原因。" },
            { "Using the last startup log on the stick to adjust this build.", "正在使用 U 盘上次的启动日志调整本次构建。" },
            { "The build stopped: ", "构建已中止：" },
            { "Engine exit code ", "引擎退出码 " },
            { "Could not read the build result (", "无法读取构建结果（" },
            { "). The saved operation report includes the engine output.", "）。已保存的操作报告包含引擎输出。" },
            { "Could not read the report: ", "无法读取报告：" },
            { "Windows did not answer the USB disk list within 30 seconds. Unplug card readers and other USB drives, then press Refresh.",
              "Windows 在 30 秒内没有返回 U 盘列表。请拔掉读卡器和其他 USB 设备，然后点刷新。" },
            { "Could not list USB sticks: ", "无法列出 U 盘：" },
            { ": 1401 is running from it", "：1401 正在从它运行" },
            { ": too small, 1401 needs 2 GB", "：容量过小，1401 需要 2 GB" },
            { "Found {0} USB stick(s).", "找到 {0} 个 U 盘。" },
            { "No USB stick found. Plug one in (4 GB or more, not the stick 1401 runs from) and press Refresh.",
              "未找到 U 盘。请插入一块（4 GB 以上，且不是 1401 当前运行所在的盘），然后点刷新。" },
            { "Disks 1401 saw and left out:", "1401 看到但已排除的磁盘：" },
            { "Board", "主板" },
            { "Processor", "处理器" },
            { "Graphics", "显卡" },
            { "Network", "网络" },
            { "check", "检测" },
            { "build", "构建" },
            { "write", "写入" },
            { "The local report is saved at ", "本地报告已保存在 " },
            { ". Scan for logs and send them can retry after restart.", "。重启后可用\"扫描日志并发送\"重试。" },
            { "The operation has no saved local report. The visible output remains available to copy.",
              "该操作没有保存本地报告。当前可见的输出仍可复制。" },
            { " The operation output may remain visible, but a durable final report is unavailable.",
              " 操作输出可能仍然可见，但无法生成可持久保存的最终报告。" },
            { "s", "" },

            // --- firmware review ---
            { "Firmware review could not be generated. No EFI or firmware was changed. The build refusal still includes storage preparation guidance.",
              "无法生成固件检查报告。未改动任何 EFI 或固件。构建拒绝信息中仍包含存储准备指引。" },
            { "Firmware review is unavailable. No EFI or firmware was changed; use the storage guidance in the build refusal.",
              "固件检查不可用。未改动任何 EFI 或固件；请参考构建拒绝信息中的存储指引。" },

            // --- writing the stick ---
            { "Plug in a USB stick and press Refresh.", "请插入 U 盘并点刷新。" },
            { "Erase {0}", "擦除 {0}" },
            { " and make it the macOS installer?\r\n\r\nEverything on it will be lost.",
              "{0}，并将其制作成 macOS 安装盘？\r\n\r\n盘上所有内容都会丢失。" },
            { "1401 - erase this stick?", "1401 - 擦除这个 U 盘？" },
            { "Writing the stick did not finish. The saved report includes the writer output; partial changes to the selected stick may remain.",
              "写入 U 盘未完成。已保存的报告包含写入器输出；所选 U 盘上可能残留部分更改。" },
            { "Package verification\r\nLaptop display note: panel wiring requires verification.\r\nIntel I225-LM vP link testing is required.",
              "软件包校验\r\n笔记本显示提示：屏幕接线需要核实。\r\nIntel I225-LM vP 需要链路测试。" },

            // --- update driver ---
            { "The NVIDIA driver is up to date.\r\n\r\n", "NVIDIA 驱动已是最新版本。\r\n\r\n" },
            { "\r\n\r\nNo 1401 stick was plugged in; plug it in and run this again to update it too.",
              "\r\n\r\n未检测到已插入的 1401 启动盘；插入后再次运行本操作即可一并更新。" },
            { "The driver could not be updated:\r\n\r\n", "驱动更新失败：\r\n\r\n" },
            { "1401 - Update driver", "1401 - 更新驱动" },

            // --- EFI doctor ---
            { "Select the drive or folder that holds your EFI folder", "选择包含 EFI 文件夹的驱动器或文件夹" },
            { "Your EFI passed every check 1401 makes.\r\n\r\n", "你的 EFI 通过了 1401 的全部检查。\r\n\r\n" },
            { "1401 found problems it cannot fix by itself:\r\n\r\n", "1401 发现了一些它无法自行修复的问题：\r\n\r\n" },
            { "\r\n\r\nFix these in your config.plist now? The current one is kept as a backup next to it.",
              "\r\n\r\n现在修复你的 config.plist 吗？原文件会作为备份保留在同目录。" },

            // --- log upload ---
            { "The {0} failed.\r\n\r\n1401 is sending this log to nullmothsystems.com so the bug can be found and fixed. " +
              "It holds this scan's hardware list, bounded device/CPU observations and what the check or build printed. Windows capabilities do not establish macOS support. Your Windows user name and PC name are removed first. " +
              "Nothing else on this PC is sent.\r\n\r\nClick OK to send it now, or Cancel to keep it only on this PC.",
              "{0}失败。\r\n\r\n1401 正在把这份日志发送到 nullmothsystems.com，以便定位并修复该问题。" +
              "日志包含本次扫描的硬件清单、有限的设备/CPU 观测结果，以及检测或构建过程的输出。Windows 的能力并不代表 macOS 一定支持。你的 Windows 用户名和计算机名会先被移除。" +
              "本机的其他任何内容都不会被发送。\r\n\r\n点\"确定\"立即发送，或点\"取消\"只保留在本机。" },
            { "1401 - sending the log", "1401 - 正在发送日志" },
            { "The log was not sent. It stays in ", "日志未发送，仍保留在 " },
            { ".", "。" },
            { "Logs sent. Report IDs ", "日志已发送。报告 ID " },
            { " - mention them in the NullMoth Discord if you ask for help.", " - 如需求助，请在 NullMoth Discord 中提及这些 ID。" },
            { "Could not send the logs (", "无法发送日志（" },
            { "). They stay on this PC.", "）。日志仍保留在本机。" },
            { "1401 - sending the startup logs", "1401 - 正在发送启动日志" },
            { "Optional: the last line on the screen when it stopped (for example \"PCI configuration begin\"):",
              "可选：停在屏幕上时最后一行显示的内容（例如 \"PCI configuration begin\"）：" },
            { "Send", "发送" },
            { "Cancel", "取消" },
            { "No logs were found. Plug in the USB stick 1401 made (the one you started macOS from) and try again.",
              "未找到日志。请插入 1401 制作的 U 盘（即你启动 macOS 时用的那块），然后重试。" },
            { "1401 found {0} diagnostic file{1} (available scan/build evidence and startup logs from attached sticks).\r\n\r\n" +
              "These retain available failure and hardware observations. 1401 is sending them to nullmothsystems.com so the bug can be found and fixed. " +
              "They hold what OpenCore and macOS printed while starting, and the stick's OpenCore settings with serial numbers removed. " +
              "An included scan receipt records saved Windows hardware observations, even if the check failed; it does not prove this PC or the attached stick has that hardware. Nothing else on this PC is sent.\r\n\r\nClick Send to send them now, or Cancel to keep them locally.",
              "1401 找到 {0} 个诊断文件{1}（来自已插入 U 盘的可用扫描/构建证据与启动日志）。\r\n\r\n" +
              "这些文件保留了可获取的故障与硬件观测信息。1401 正在把它们发送到 nullmothsystems.com，以便定位并修复该问题。" +
              "它们包含 OpenCore 和 macOS 启动时打印的内容，以及移除序列号后的 U 盘 OpenCore 设置。" +
              "其中的扫描回执记录了已保存的 Windows 硬件观测结果，即使检测失败也会有；它不能证明本机或所插 U 盘具备这些硬件。本机的其他任何内容都不会被发送。\r\n\r\n点\"发送\"立即发送，或点\"取消\"仅保留在本地。" },
            { "Sent ", "已发送 " },
            { " log(s). Report ID ", " 份日志。报告 ID " },
            { " - mention it in the NullMoth Discord if you ask for help.", " - 如需求助，请在 NullMoth Discord 中提及它。" },
            { "The logs could not be sent: ", "日志无法发送：" },
            { "\r\nThey are still where they were; try again with Scan for logs and send them.",
              "\r\n它们仍在原处；可用\"扫描日志并发送\"重试。" },
            { "Saved reports could not be listed (", "无法列出已保存的报告（" },

            // --- engine / packaging ---
            { "The engine folder is missing next to 1401.exe (engine\\python\\python.exe). Copy the whole 1401 folder, not just the exe.",
              "1401.exe 旁边缺少引擎文件夹（engine\\python\\python.exe）。请复制整个 1401 文件夹，而不只是 exe。" },
            { "The engine folder is incomplete (engine\\app\\p1401).", "引擎文件夹不完整（engine\\app\\p1401）。" },

            // --- crash handler ---
            { "A local crash report was saved at ", "本地崩溃报告已保存在 " },

            // --- USB disk listing ---
            { "Disk {0}:  {1}  -  {2:0.#} GB{3}", "磁盘 {0}：  {1}  -  {2:0.#} GB{3}" },
            { "connected by ", "连接方式为 " },
            { ": connected by ", "：连接方式为 " },
            { ", not USB", "，不是 USB" },
            { ": Windows runs from it", "：Windows 正从它启动" },
            { "bus ", "总线类型 " },
        };

        static readonly string Forced = Environment.GetEnvironmentVariable("A1401_LANG");

        /// <summary>"zh" when the UI language is Chinese and translations are loaded, otherwise "en".
        /// Chinese is the only translated language so far; everything else keeps the original wording.</summary>
        public static readonly string Language =
            (Forced ?? CultureInfo.CurrentUICulture.Name ?? "").StartsWith("zh", StringComparison.OrdinalIgnoreCase) ? "zh" : "en";

        /// <summary>The English string, or its translation when the UI language is Chinese.
        /// A key with no translation returns itself, so the UI never shows an empty label.</summary>
        public static string T(string en)
        {
            if (en == null || Language != "zh") return en;
            string zh;
            return Zh.TryGetValue(en, out zh) && !string.IsNullOrEmpty(zh) ? zh : en;
        }

        /// <summary>The operation name in a message ("the check failed"), translated on its own.</summary>
        public static string Op(string en)
        {
            switch (en)
            {
                case "check": return T("check");
                case "build": return T("build");
                case "write": return T("write");
                default: return en;
            }
        }

        /// <summary>A translated string with {0}-style holes filled. The holes stay in the same
        /// order and count in every language, so a translated template can never drop an argument.</summary>
        public static string F(string en, params object[] args)
        {
            var t = T(en);
            for (int i = 0; i < args.Length; i++)
                t = t.Replace("{" + i + "}", "" + args[i]);
            return t;
        }
    }
}