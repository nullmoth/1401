# 1401-HUAWEI 项目报告总览

本目录是本次工程的完整中文交付记录。所有结论按证据等级标注：

| 等级 | 含义 |
|---|---|
| **本机实测** | 在目标 Huawei MateBook X Pro 2023（MRGFG-XX，i7-1360P）上实际执行并留有日志/JSON |
| **源码验证** | 阅读并跟踪了实际代码路径，由测试或构建结果证明 |
| **文档/上游** | 来自官方文档、上游仓库或公开资料，未在本机复现 |
| **待实机验证** | 需要真实 macOS 启动/安装才能确认，本项目未伪造结果 |

## 结论摘要

- 已建立自有 Fork：`origin = https://github.com/a137460387/1401.git`，`upstream = https://github.com/nullmoth/1401.git`。
- 基线核实：官方 `v2.9` 标签 = `03c79ef772f6142d59eb5203ce0efa98845bd0ba`，与 `upstream/main` 和 `origin/main` 一致；官方 Release `v2.9` 的 `target_commitish` 也是该 SHA。
- 已在 Windows 11 原生环境构建 `1401.exe`（.NET SDK 8.0.425，net48/WinForms），版本 2.9.1。
- 已对真实 MateBook 执行官方硬件扫描，生成 `out/huawei-scan/Report.json` 与 ACPI 表（含 DSDT）。
- 已用官方引擎为真实扫描生成 OpenCore EFI：SMBIOS `MacBookPro16,2`，23 个 kext 名称（30 个 Kernel/Add 条目含插件），11 个 ACPI 表，5 个驱动；`ocvalidate` 0 问题。
- 已修复 6 类可复现问题（P0 擦盘身份、Windows 参数拼接、大容量盘确认、完整安装器 416/越界、Recovery 擦盘前校验、依赖缓存不可写），每项有独立提交与回归测试。
- 华为适配：A7A0 已由生成器选中 WhateverXe；AX211/itlwm 的安装器联网判定已修正；UTBDefault 无 map 已明确报告；TPD0/TPL1 已分开说明；TBU405Pro 外置盘已标记为“非安装目标”。
- 完整测试：**1190 项，0 失败，8 项环境/可选依赖跳过**（OpenCore 1.0.8 归档、可选驱动包、DSDT 语料等）。
- 未验证/外部边界：真实 macOS 启动与安装、WhateverXe 图形加速、AX211 在 macOS 下的 Wi-Fi、I2C 触摸板/触摸屏、USB 外置盘 UASP/睡眠唤醒、18 GB 完整安装器实际下载与可启动介质、标准 Apple `createinstallmedia` 离线盘（需 macOS）。
- 未执行任何真实磁盘写入：aigo U350、ACASIS TBU405Pro、WD SN740 均未修改。

## 目录

| 路径 | 内容 |
|---|---|
| `source/` | 源码结构、依赖、许可证、Windows 开发环境与构建 |
| `bugs/` | GitHub 历史问题审计、已修复清单、未修复与阻塞 |
| `hardware/` | 真实硬件扫描、适配矩阵、EFI 生成与文件级验证 |
| `recovery/` | Recovery 下载/校验证据、EXITBS 与 root_hash 分析、完整安装器边界 |
| `tests/` | T0–T6 测试体系、1188 项测试结果、构建与打包验证 |
| `releases/` | 版本说明、回滚方案、上游同步操作说明 |
| `logs/` | 原始命令日志（构建、测试、扫描、验证） |

## 关键原始证据

- `reports/logs/huawei-scan.log`：真实硬件扫描。
- `reports/logs/huawei-build-release.log`：真实扫描生成发布 EFI 的完整 JSON 结果与通知。
- `reports/hardware/efi-file-check.json`：EFI 文件级检查 + `ocvalidate`。
- `reports/recovery/verification.json`：Apple Recovery 与完整安装器的真实网络证据。
- `reports/logs/unittest-final2.log`：1188 项测试最终结果。
- `reports/logs/release-prepare*.log`、`reports/tests/windows-verification.json`：Windows 打包验证（见对应报告）。
