# 02 8086:A7A0、Raptor Lake-P 与 Tahoe 26 的证据

## 1. 官方资料（读取日期 2026-11-11）

### 1.1 WhateverXe 0.8.0

来源：<https://github.com/b00t0x/WhateverXe/blob/0.8.0/README.md>

兼容性表：

| macOS | Required version |
|---|---|
| Big Sur | 11.7.11 |
| Monterey | 12.7.6 |
| Ventura | 13.7.8 |
| Sonoma | 14.8.9 |
| Sequoia | 15.8.x |
| **Tahoe** | **26.7 or newer** |

“Tested on hardware”原文只列到：

> - Tiger Lake-U: 48- and 80-EU configurations.
> - Alder Lake-N: 16- and 24-EU configurations.
> - Twin Lake: 32-EU configurations.
> - Alder Lake-H: 96-EU configurations, including single-channel operation.
> - Alder Lake-S: UHD Graphics 770.
> - **Raptor Lake-U: 48-EU configurations.**

“Expected to work, not yet tested on hardware”原文：

> - Other supported Tiger Lake-U/H35 configurations, including 96 EU, and Tiger Lake-H45.
> - Other supported Alder Lake-N / Twin Lake configurations.
> - **Other supported Alder Lake-H/P/U and Raptor Lake-H/P/U configurations.**
> - Other supported Alder Lake-S/HX and Raptor Lake-S/HX configurations.
> - **Internal eDP on Alder Lake-N / Twin Lake and Alder Lake-H/P/U / Raptor Lake-H/P/U is implemented but has not been tested on hardware.**

换句话说，A7A0 属于 **Raptor Lake-H/P**，在官方“预期能工作、但未实机验证”的范围内；官方明确说
Raptor Lake-H/P/U 的内部 eDP 已实现但未实测。

### 1.2 官方设备选择表

来源：<https://github.com/b00t0x/WhateverXe/blob/0.8.0/docs/device-selection.md>

原文把 A7A0 列在：

> “Raptor Lake-H / P”: `A720`, `A7A0`, `A7A8`, `A7AA`, `A7AB`

同一页的 Notes：

> “An implemented backend does not imply hardware validation for every ID or connector.”

> “Raptor Lake-U internal DSI and acceleration have been verified on MiniBook X U300 (`A7A9`) with Big Sur and Tahoe.”

注意：这条唯一被点名的 Raptor Lake 实机验证是 **Raptor Lake-U A7A9 + MIPI DSI**，不是 A7A0，也不是 eDP，
更不是 3120×2080@90 Hz。

### 1.3 WhateverXe Graphics v0.4.1

来源：<https://github.com/b00t0x/WhateverXe-Graphics/blob/v0.4.1/README.md>

Requirements 原文：

> - OpenCore with Lilu, the latest WEX and AMFIPass 1.4.1 Mod. Upstream AMFIPass is not a substitute.
> - SIP setting `csr-active-config=03080000` (`0x803`). Full SIP is unsupported.

兼容性表与 WEX 相同，Tahoe 要求 **26.7 or newer**。

Install 原文：

> 1. Configure OpenCore as described in WEX. Restore any older Xe System patch first.
> 2. Boot the target macOS and open `WhateverXe-Graphics-*.pkg` from Releases.
> 3. Restart after installation succeeds.

> The installer does not change EFI or SIP.

这最后一句很关键：**Graphics 安装器不会替你改 EFI 或 SIP**。所以 EFI 必须在启动 macOS 之前就已经有
`0x803`，否则安装器没有义务、也没有能力补上。

## 2. 1401 对 A7A0 的识别

### 2.1 分类表

`p1401/intel_gpu.py:29-35` 的 `WHATEVERXE_IDS` 包含 60 个 ID，A7A0 在列；`p1401/intel_gpu.py:46` 把它归入
`Raptor Lake-P (Xe-LP)`。

`tests/test_intel_gpu.py` 保证：

- 60 个 ID 都能分类；
- `p1401/intel_gpu.py`、`mac/Sources/main.swift` 的 `App.xeIds`、`mac/Resources/nullmoth-setup.sh` 的
  case 列表三者一致。

### 2.2 上游选择阈值

`upstream/OpCore-Simplify/Scripts/compatibility_checker.py:128-130` 对 WhateverXe ID 把最低 macOS 版本设为
`20.0.0`，避免被上游判成“无驱动”而退出。`kext_maestro.py:419-431` 再按
`Device Type` 含 `Integrated GPU`、厂商 Intel、`Device ID[5:]` 在 `WhateverXeDeviceIDs` 中选中 WEX。

真实扫描的 `Device Type` 是 `Integrated GPU`，所以命中。构建日志
`reports/logs/huawei-build-release.log:61` 记录了“Found Intel(R) Iris(R) Xe Graphics is Intel Raptor Lake-P GPU”。

### 2.3 结论

| 问题 | 结论 | 证据等级 |
|---|---|---|
| 1401 是否识别 A7A0？ | 是 | 源码验证 + 真实构建日志 |
| OpCore 是否为 A7A0 选择 WEX？ | 是 | 源码验证 + EFI 文件 |
| 官方是否把 A7A0 列为支持的设备 ID？ | 是（Raptor Lake-H/P） | 文档/上游 |
| 官方是否实测过 A7A0？ | **否**（只实测 Raptor Lake-U A7A9） | 文档/上游 |
| 官方是否实测过 Raptor Lake-H/P/U 的内部 eDP？ | **否**（明确写 implemented but not tested） | 文档/上游 |
| 这台机器的 3120×2080@90 Hz eDP 是否被验证？ | **未知** | 无任何本机/上游证据 |

## 3. 这台机器的具体面板

`out/huawei-scan/Report.json`：

```json
"Monitor": {
  "CSO1415": {
    "Connector Type": "Internal",
    "Resolution": "3120x2080",
    "Connected GPU": "Intel(R) Iris(R) Xe Graphics"
  }
}
```

扫描没有记录刷新率；90 Hz 来自用户提供的机器规格，不是本项目实测。上游 WhateverXe 的已测内部面板是：

- GPD MicroPC 2 / CHUWI MiniBook X N100：MIPI DSI，16/24 EU，最高 60 Hz；
- CHUWI MiniBook X U300：MIPI DSI，Raptor Lake-U 48 EU，内部面板 50 Hz，可选 60 Hz；
- 没有任何 Raptor Lake-P/H + eDP + 3120×2080 + 90 Hz 的公开验证。

因此对这台机器只能写：

> **A7A0 的 WEX 后端已实现；内部 eDP 在 Raptor Lake-H/P/U 上已实现但官方未实测；本机的 eDP 3120×2080@90 Hz 属于未知，不能承诺 90 Hz、HiDPI 或亮度正常。**

## 4. Tahoe 26 的版本分析

### 4.1 官方支持范围

WhateverXe 0.8.0 和 WhateverXe Graphics v0.4.1 都要求：

- Sequoia：15.8.x（不是 15.0–15.7）；
- Tahoe：**26.7 或更新**（不是 26.0–26.6）。

这一点常被“macOS 26 Tahoe”这个大类掩盖。`26.0`、`26.1`……`26.6` 都不在上游支持范围内。

### 4.2 1401 的构建目标与门槛

- 1401 的 `--macos 25` 表示 Darwin 主版本 25，即 macOS 26 Tahoe；构建结果 `macos_version=25.99.99`
  （见 `reports/hardware/03-EFI生成与验证.md`）。
- 这个主版本号**不能表达 26.7**。因此：
  - Mac App 的 `nullmoth-setup.sh:1402-1403` 用 `sw_vers -productVersion` 精确检查：
    `15.8+` 或 `26.7+`，否则 `stop`；`mac/tools/test_xe_whateverxe.py` 有 `26.6.2` 被拒绝的用例。
  - Windows 构建器在修复前把 WEX 的 `MinKernel` 留成 `20.0.0`，因此 26.0–26.6 也会加载 WEX；
  - 本次修复后，Tahoe 构建把 WEX `MinKernel` 设为 `25.7.0`（Darwin 25.7 = macOS 26.7），26.0–26.6
    启动时 WEX 条目不匹配，macOS 走 firmware framebuffer（基本显示），不会加载作者未支持的驱动。

### 4.3 候选 EFI 的实际值

```text
WhateverXe.kext  Enabled=true  MinKernel=25.7.0  MaxKernel=""
```

`scripts/verify_efi.py` 检查 `WhateverXe Tahoe MinKernel is 25.7.0`；候选 EFI 通过。

### 4.4 仍需用户确认的事项

- 用户实际写入 U 盘的 macOS 安装器必须是 **26.7 或更新**；构建器无法从“Tahoe 26”大类推断补丁号。
- 如果安装器是 26.0–26.6：
  - WEX 不会加载（本次修复后），系统走 firmware framebuffer；
  - 不会加速，但也不会加载官方不支持的 WEX；
  - Mac App 的 `--xe` 会以“26.7 or later”拒绝安装 Graphics。
- 如果安装器是 26.7+，WEX 可以加载；Graphics 仍需 macOS 内安装。

## 5. 结论：已实测 vs 预期

| 项目 | 状态 | 说明 |
|---|---|---|
| A7A0 在 1401/OpCore/官方设备表 | **已确认** | 源码 + 官方文档 |
| Windows 构建器为 A7A0 选 WEX | **已确认** | 真实构建日志 + EFI 文件 |
| WEX 0.8.0 kext 在 A7A0 上加载 | **未实测** | 需要真机启动 |
| A7A0 的 Metal / OpenGL / 视频解码 | **未实测** | 上游未点名 A7A0 |
| A7A0 内部 eDP 点亮 | **未实测** | 官方明确 implemented but not tested |
| 3120×2080@90 Hz | **未知** | 无任何公开或本机证据 |
| 亮度控制（SSDT-PNLF） | **未实测** | 表已放入 EFI，效果未知 |
| WhateverXe Graphics 安装 | **未实测** | 需要 macOS 内运行 |
| 睡眠/唤醒、外接显示器 | **未实测** | 上游本身标为 experimental/known issues |

**不能把“官方预期支持”写成“已经实测支持”。** 本报告和候选 EFI 的通知都按这个边界表述。
