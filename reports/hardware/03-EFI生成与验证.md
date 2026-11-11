# EFI 生成与文件级验证（真实 MateBook 扫描）

## 1. 生成命令

```powershell
.\.venv\Scripts\python.exe -m p1401 build `
  out\huawei-scan\Report.json out\huawei-scan\ACPI out\huawei-efi-release `
  --macos 25 --json
```

说明：macOS 26 Tahoe 的 Darwin 主版本是 **25**。首次错误地传 `--macos 26`，引擎明确返回
`MacosNotOffered: ... Darwin 26 is not among them. Pick macOS 26 Tahoe ...`，没有生成半成品 EFI；改为 25 后成功。

结果：`ok=true`，`smbios=MacBookPro16,2`，`macos_version=25.99.99`（Darwin 25 → macOS 26 Tahoe）。

## 2. 生成内容

| 项 | 结果 |
|---|---|
| EFI 目录 | `out/huawei-efi-release/EFI` |
| SMBIOS | **MacBookPro16,2** |
| 目标 macOS | 25.99.99（Tahoe 26） |
| Kernel/Add 条目 | **30**（23 个主 kext 名称 + VoodooI2C/PS2 插件等） |
| ACPI/Add | **11**：SSDT-ALSD、SSDT-SBUS、SSDT-EC、SSDT-GPI0、SSDT-MCHC、SSDT-PLUG-ALT、SSDT-PNLF、SSDT-RTCAWAC、SSDT-USB-Reset、SSDT-USBX、SSDT-XOSI |
| UEFI/Drivers | **5**：apfs_aligned.efi、HfsPlus.efi、OpenCanopy.efi、OpenRuntime.efi、ResetNvramEntry.efi |
| 主 kext | Lilu、VirtualSMC、SMCBatteryManager、SMCLightSensor、SMCProcessor、SMCSuperIO、**WhateverXe**、**itlwm**、BlueToolFixup、IntelBluetoothFirmware、IntelBTPatcher、USBToolBox、**UTBDefault**、XHCI-unsupported、VoodooPS2Controller、VoodooI2C、VoodooI2CHID、NVMeFix、AMFIPass、BrightnessKeys、CpuTopologyRebuild、ECEnabler、RestrictEvents |
| boot-args | `-v debug=0x100 keepsyms=1 -allow3d -disablegfxfirmware -igfxdvmt -vi2c-force-polling ctrsmt=full -ibtcompatbeta revpatch=sbvmm` |

关键 quirks（实际 `config.plist`）：

| 项 | 值 | 说明 |
|---|---|---|
| `Booter/Quirks/DevirtualiseMmio` | `false` | 通用混合核心笔记本规则 |
| `Booter/Quirks/SetupVirtualMap` | `true` | 上游选择 |
| `Booter/Quirks/RebuildAppleMemoryMap` | `true` | 上游选择 |
| `Booter/Quirks/SyncRuntimePermissions` | `true` | 上游选择 |
| `Kernel/Quirks/ProvideCurrentCpuInfo` | `true` | Huawei 配方 |
| `Kernel/Quirks/DisableIoMapper` | `true` | 上游选择 |
| `Kernel/Quirks/AppleXcpmCfgLock` | `true` | 上游选择 |
| `Kernel/Emulate/Cpuid1Data` | `55060a00000080000000000000000000` | byte 6 = **0x80 (128)** |
| `Kernel/Emulate/Cpuid1Mask` | `ffffffff0000ff000000000000000000` | byte 6 = **0xFF** |

Huawei 配方的应用结果：`Cpuid1Data[6]=128`、`Cpuid1Mask[6]=255`、`ProvideCurrentCpuInfo=true` 均在最终 EFI 中。配方状态为 `theory`：同 CPU 的 XPS 9320 已验证，本机尚未启动 macOS。

## 3. 构建通知（真实输出摘要）

- Raptor Lake-P A7A0 在 WhateverXe 设备表；EFI 含 WhateverXe；完整图形包是安装后 opt-in（macOS 15.8/26.7+）。
- AX211 8086:51F1 使用 itlwm，需 HeliPort；安装器不能用它，建议以太网或完整离线安装器。
- GXTP786 是 I2C 触摸板；VoodooI2C/HID + VoodooPS2 + `-vi2c-force-polling` 已包含；它不是触摸屏。
- GXTP738X 是 I2C 触摸屏，不是触摸板；macOS 无触摸屏驱动，不承诺可用。
- TBU405Pro（953.9 GiB，USB）是外置 USB NVMe，不是内部安装目标；需在 Disk Utility 抹 APFS，从 U 盘 OpenCore 启动；UASP/睡眠/外置启动未验证。
- USB：使用 UTBDefault（全端口）且没有 UTBMap；睡眠/端口可能异常；可用 USBToolBox 生成 map 后 `--utbmap` 重建。
- 通用：itlwm 需 HeliPort。
- SMBIOS：MacBookPro16,2。
- 离线安装器提示：无以太网 + itlwm，安装器需联网。

## 4. 文件级验证结果

脚本：`scripts/verify_efi.py out/huawei-efi-release --json-out reports/hardware/efi-file-check-release.json`

```json
{
  "ok": true,
  "errors": [],
  "counts": {"kexts": 30, "acpi": 11, "drivers": 5},
  "sha256": {
    "EFI/OC/config.plist": "f1b65f6bceac80c1d3f986d898664746ecc36e3cab2ec1d31b536a83f7865bc5",
    "EFI/OC/OpenCore.efi": "5af6acdaabdf02f8727fd3ee2aac3ae8388f4059ce939970e167a503d12aa82a"
  }
}
```

检查项包括：8 个 OpenCore 配置段、3 个必需文件、每个 kext/ACPI/驱动条目可解析、Huawei 相关 kext 存在、5 张关键 ACPI 表、3 个 boot-arg、CPUID 两字节、SMBIOS、`DevirtualiseMmio=false`、`DisableIoMapper=true`，以及 `ocvalidate`。

`ocvalidate`（与 EFI 同版本 OpenCore 1.0.9）：

```
Completed validating config.plist in 2 ms. No issues found.
```

## 5. 生成过程的可复现性问题（已修复）

- 第一次成功选择后，重复构建在 `OCK_Files/Lilu/manifest.json` 报 `PermissionError`：根缓存可写、子目录 ACL 拒绝。修复后选择 `OCK_Files-2`，同一构建成功。见 `bugs/02` FIX-06。
- 首次 `--macos 26` 是参数语义错误（Darwin 主版本），不是代码缺陷；已记录。
- 构建期间 `iasl` 报告 DSDT 有重复名称、248 个外部方法未解析；构建继续且不使用预补丁反汇编。该 ACPI 警告列入待实机/后续项。

## 6. 边界

本报告只证明 **EFI 文件生成正确、条目完整、ocvalidate 通过**。它**不证明**：

- 该 EFI 能在本机启动 OpenCore；
- macOS 能启动、安装、进入桌面；
- WhateverXe 提供图形加速；
- Wi-Fi/触摸板/触摸屏/外置盘在 macOS 下可用；
- 睡眠/唤醒正常。

这些需要用户授权真实写盘并重启，见 `bugs/03`。
