# WhateverXe / Huawei 图形加速专项审计

审计对象：本仓库（1401 Huawei Fork）与已发布的 `v2.9.1-huawei.1` 源码/构建器。
目标机器：Huawei MateBook X Pro 2023（MRGFG-XX，i7-1360P，Iris Xe `8086:A7A0`，32 GB，3120×2080@90 Hz eDP）。
目标系统：macOS Tahoe 26。

证据等级沿用本仓库 `reports/README.md` 的定义：**本机实测**、**源码验证**、**文档/上游**、**待实机验证**。
本审计没有向任何真实磁盘写入、没有部署 EFI、没有修改 BIOS、没有安装 macOS、没有重启电脑。

## 最终回答（先给结论）

**按已发布的 `v2.9.1-huawei.1`：不具备“开箱即用”的 WhateverXe 图形加速 EFI 生成能力。**

原因不是“EFI 里没有 WhateverXe”——Windows 构建器确实会为 A7A0 选中并放入 `WhateverXe.kext`、Lilu 和
AMFIPass Mod——而是它生成的示例 EFI 把 `csr-active-config` 降到了 `0x00000003`，缺少 WhateverXe 0.8.0 和
WhateverXe Graphics v0.4.1 明确要求的 `0x800` 位（官方要求 `0x803`）；同时 Windows 端没有固定 WhateverXe
版本，也没有安装 WhateverXe Graphics 的能力。

**按本次审计修复后的源码/候选 EFI：EFI 侧的 WhateverXe 前置条件已经具备（有条件）。**

候选 EFI 已满足：WhateverXe 0.8.0（固定 SHA-256）、AMFIPass 1.4.1 Mod（固定 commit + SHA-256）、Lilu 在前、
WhateverGreen 关闭、`-allow3d -disablegfxfirmware`、SIP 含 `0x803` 位（实际 `0x0A03`）、Tahoe 构建 `MinKernel
25.7.0`、`SSDT-PNLF` 存在。但它仍然**不是**一个“只靠 EFI 就能加速”的交付物：加速所需的 WhateverXe Graphics
v0.4.1 包必须在 macOS 启动后由 1401 Mac App 安装；而且 b00t0x 只实测了 Raptor Lake-U，A7A0 和这条内部 eDP
属于“已实现、未实机验证”。

因此严格表述是：

> **当前发布的 1401：否。**
>
> **本次修复后的候选：EFI 侧是；整机“已加速”仍需 macOS 内安装 WhateverXe Graphics，且 A7A0/eDP 未实测，不能宣称已验证。**

## 交付物索引

| # | 交付物 | 位置 |
|---|---|---|
| 1 | WhateverXe 集成现状审计报告 | `01-集成审计.md` |
| 2 | 8086:A7A0 支持情况及证据 | `02-A7A0与Tahoe26.md` |
| 3 | Windows EFI Builder 集成缺口清单 | `01-集成审计.md` 第 9 节 |
| 4 | Tahoe 26 兼容性分析 | `02-A7A0与Tahoe26.md` 第 5 节 |
| 5 | 已修复问题及提交记录 | 本文“代码提交”；`01-集成审计.md` 第 10 节 |
| 6 | 自动化测试和校验结果 | `03-候选EFI与测试.md` |
| 7 | 独立 Huawei EFI 候选版本 | `out/huawei-efi-whateverxe-audit/`；见 `03-候选EFI与测试.md` |
| 8 | 实机启动前风险清单 | `04-风险与未验证.md` |
| 9 | 尚未实机验证的事项清单 | `04-风险与未验证.md` |

## 候选 EFI

- 路径：`out/huawei-efi-whateverxe-audit/EFI`
- 生成命令：`.venv/Scripts/python.exe -m p1401 build out/huawei-scan/Report.json out/huawei-scan/ACPI out/huawei-efi-whateverxe-audit --macos 25 --json`
- 独立于 2.9.1 正式发布 EFI：未覆盖、未移动 `out/huawei-efi-release/`，未触碰 `v2.9.1-huawei.1` 标签或发布资产。
- `config.plist` SHA-256：`c70105907a6fb5fc11d2efc1a136876d8ba6fa348b0d253143412c72df3b83c3`
- `OpenCore.efi` SHA-256：`5af6acdaabdf02f8727fd3ee2aac3ae8388f4059ce939970e167a503d12aa82a`
- 文件级校验：`reports/hardware/efi-file-check-whateverxe-audit.json`，82 项全部通过，`ocvalidate` 0 问题。
- 与 2.9.1 示例 EFI 的配置差异只有 `csr-active-config`（`03→0A03`）和本次新建 EFI 的 SMBIOS 身份字段
  （序列号/MLB/ROM/UUID）；kext、ACPI、驱动与 boot-args 结构一致。

## 代码提交

- `01d8ab6` `WhateverXe: pin releases, enforce its SIP/deps, fix second-run SIP guard`
- 分支：`audit/whateverxe-huawei`
- 涉及的正式发布标签 `v2.9.1-huawei.1` 未移动、未重新打包、未替换资产。

## 关键证据入口

- 发布示例 EFI 的 SIP 缺陷：`reports/logs/huawei-build-release.log:9171-9174`（`030a0000 → 03000000`），
  `out/huawei-efi-release/EFI/OC/config.plist`（`csr-active-config = 03 00 00 00`）。
- 用新增 WEX 检查跑发布示例 EFI：`reports/hardware/efi-file-check-release-whateverxe.json`，只有
  `SIP includes 0x803: 0x0003` 与 `MinKernel: 20.0.0` 两项失败。
- 发布资产内的旧逻辑：`1401-Windows-2.9.1.zip` → `1401/engine/app/p1401/policy.py:660-661`；
  `1401/NullMoth/1401-Mac-2.9.zip` → `nullmoth-setup.sh:1408`（没有本次的 SIP 前置保护）。
- 发布示例 EFI 的 WhateverXe：`reports/hardware/efi-file-check-release.json:161,256`；kext 版本 0.8.0。
- 候选 EFI 的 WEX 下载与 SHA 校验：`out/huawei-efi-whateverxe-audit-build.json` 的构建上下文
  （`WhateverXe-0.8.0-RELEASE.zip`、`AMFIPass-v1.4.1-Mod-RELEASE.zip`，均 `Checksum verified successfully`）。
- 上游支持表：<https://github.com/b00t0x/WhateverXe/blob/0.8.0/README.md>、
  <https://github.com/b00t0x/WhateverXe/blob/0.8.0/docs/device-selection.md>、
  <https://github.com/b00t0x/WhateverXe-Graphics/blob/v0.4.1/README.md>。
