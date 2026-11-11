# EXITBS:START 与 usr\standalone\OS.dmg.root_hash 分析

结论先行：**这两条日志不是同一个故障，也没有因果关系。** `EXITBS:START` 是 Apple `boot.efi` 的 ExitBootServices 阶段日志；`OS.dmg.root_hash` 是 `boot.efi` 在 Preboot 卷查找密封系统卷根哈希的预检。安装介质上后者的 `Err(0xE)` 很常见，**不能**据此判断 Recovery 文件损坏，也**不能**用“重做 U 盘”修复。

## 1. `[EB|LOG:EXITBS:START]` 是什么

- 带 `AAPL:`/`[EB|...]` 前缀的行是 **Apple `boot.efi` 的输出**，由 OpenCore 的 `AppleDebug` 选项转发到 OpenCore 日志，不是 OpenCore 自己的阶段。
  来源：OpenCore `Docs/Configuration.tex` 中 `AppleDebug` 说明
  <https://github.com/acidanthera/OpenCorePkg/blob/master/Docs/Configuration.tex#L3949-L3955>
- `EXITBS:START` / `EXITBS:END` 是 `boot.efi` 的 `bootercfg` 日志阶段（`0x0A`/`0x0B`）；`serial=1` 只从 `EXITBS:END` 起输出，`serial=2` 从 `EXITBS:START` 起输出。
  来源：同文件 `bootercfg` 段
  <https://github.com/acidanthera/OpenCorePkg/blob/master/Docs/Configuration.tex#L5254-L5267>
  <https://github.com/acidanthera/OpenCorePkg/blob/master/Docs/Configuration.tex#L5329-L5338>
- 因此，**磁盘上的 `opencore-*.txt` 停在 `EXITBS:START` 并不等于系统停在那里**；很多成功启动的日志也停在该行，因为后续输出走串口。要判断是否真的卡住，需要：
  1. 屏幕/串口是否继续输出；
  2. 是否出现 `EXITBS:END`；
  3. 是否进入内核 verbose/panic。
  社区日志例子：<https://github.com/dssoftx/Hackintosh-X1Carbon-G11-IrisXe-Tahoe/blob/main/CHANGELOG-X1C.md>
  LogCheck 示例：<https://github.com/corpnewt/LogCheck/blob/master/README.md>

### 真正停在 EXITBS 附近的已知类别

Dortania 的 EXITBS 专节：<https://dortania.github.io/OpenCore-Install-Guide/troubleshooting/extended/kernel-issues.html#stuck-on-eb-log-exitbs-start>

| 类别 | 说明 | 与本机的关系 |
|---|---|---|
| MMIO / `DevirtualiseMmio` | 某些 TRx40 需要开；部分 X99/新固件开了反而坏；可用 `MmioWhitelist` | 本机 EFI 为 `false`（通用混合核心笔记本规则） |
| 内存映射 | `SetupVirtualMap`、`RebuildAppleMemoryMap`、`SyncRuntimePermissions`、`EnableWriteUnprotector` 的组合 | 本机为 `true/true/true/false`，属常见组合 |
| CPU/CPUID/CFG | 缺 CPU 补丁、CFG lock、`ProvideCurrentCpuInfo`/拓扑 | 本机 `ProvideCurrentCpuInfo=true`，Huawei 配方将 CPUID 逻辑处理器设为 128（`theory`） |
| VT-d / `DisableIoMapper` | OpenCore 文档建议开 `DisableIoMapper`、关 VT-d 或移除 DMAR | 本机 `DisableIoMapper=true` |
| GPU/kext | 社区经验：dGPU/WhateverGreen 等可在 handoff 后冻结；非 OpenCore 文档的独立类别 | 本机仅 iGPU + WhateverXe；无 dGPU |
| 虚拟机 | VMware 15 会停在 EXITBS:START，16 修复 | 不适用（本机物理机） |

> “CPU 核心数必须是 2 的幂”等说法是社区经验，不是 OpenCore 文档结论；本报告不把它当作事实。

## 2. `usr\standalone\OS.dmg.root_hash` 是什么

- `boot.efi` 的 `AAPL: #[EB|RH:PF] ... usr\standalone\OS.dmg.root_hash` + `EB.LD.OFS|OPEN! Err(0xE)` 是**根哈希预检**，由 `AppleDebug` 转发。
  例子：<https://github.com/corpnewt/LogCheck/blob/master/README.md>
- Apple `bless` 源码把它称为 “ARV root hash path within Preboot volume on Intel Macs”；`bless` 在 Preboot 卷按系统卷 UUID 查找该文件，并把存在性当作 ARV/密封语义，文件内容用于取密封快照名。
  <https://github.com/apple-oss-distributions/bless/blob/main/libbless/bless_private.h#L91-L102>
  <https://github.com/apple-oss-distributions/bless/blob/main/libbless/APFS/BLAPFSUtilities.c#L641-L676>
  <https://github.com/apple-oss-distributions/bless/blob/main/blessUtilities.c#L629-L663>
- Apple 对“签名系统卷（SSV）”的定义：根节点哈希覆盖系统卷每个字节，启动时校验；安装/更新时在设备上重新计算。
  <https://support.apple.com/guide/security/signed-system-volume-security-secd698747c9/web>
- `macrecovery.py` 只下载/校验 `BaseSystem.dmg` 与 `BaseSystem.chunklist`，从不下载目标卷的 root hash。
  <https://github.com/acidanthera/OpenCorePkg/blob/master/Utilities/macrecovery/macrecovery.py#L86-L125>
- 结论（标注为推断）：`OS.dmg.root_hash` 是**目标盘 Preboot 卷上的密封产物**，不是 `BaseSystem.dmg` 的成员，也不是完整安装器下载的文件；安装器在目标上完成密封时才生成/更新它。

### 为什么安装介质上会看到 Err(0xE)

- 安装介质尚无“已安装的密封系统卷”，预检打开失败后 `boot.efi` 继续到 `EXITBS:START`；维护者和社区把该行视为安装介质的常见/无害输出。
  <https://github.com/acidanthera/bugtracker/issues/2120>
- 该行发生在 `EXITBS:START` **之前**；同一份日志随后可能因完全无关的原因停住。
  <https://github.com/acidanthera/bugtracker/issues/2559>
- 已安装卷上密封缺失/损坏才意味着 SSV 真故障，启动会停并提示重装（Apple SSV 文档）。
- 把安装失败归因于 root_hash、或声称“重做 U 盘会重建 root hash”没有依据。旧版 `docs/TROUBLESHOOTING.md` 的这条说法已在本 Fork 修正。

## 3. 对 MateBook 的实际建议

如果本机在 `EXITBS:START` 附近停住：

1. **先确认是否真的停住**：接串口或看屏幕；磁盘日志停在 START 本身不是证据。OpenCore 的 `bootercfg`/`serial` 可打开串口日志。
2. **不要因为 `OS.dmg.root_hash` 重做 U 盘**；它不是原因。
3. 按 Dortania EXITBS 顺序检查：内存映射 quirks、`DevirtualiseMmio`、VT-d/`DisableIoMapper`、CPU 拓扑/CPUID、GPU/kext。
4. 本机特定：Huawei 配方的 `ProvideCurrentCpuInfo + CPUID 128` 是 `theory`；若 E-cores 下冻结，优先复核它（可临时在 BIOS 关 E-cores/HT 做对照）。
5. 若内核已启动后黑屏/Setup Assistant 不渲染（#86/#60），那是图形路径，不是 EXITBS；用 `finish-setup.sh` 完成首次安装，再装图形包。
6. 若在线 Recovery 安装失败（#127），用完整安装器路径；它解决“Recovery 内存盘装不下 18 GB”的问题，不解决 root_hash/SSV。

## 4. 1401 在本项目中实际保证的与不保证的

**保证（源码+实测）**：
- `BaseSystem.chunklist` 用 Apple EFI ROM RSA 公钥验签；逐块 SHA-256；预检取完整首块并比对哈希（本项目修复）。
- 本地镜像在擦盘前完整校验（本项目修复）。
- 下载后读回校验（镜像路径使用无缓冲读）。
- 完整安装器目录、真实 URL、HTTP Range 206（本项目实测）。

**不保证**：
- `OS.dmg.root_hash` 的生成/修复；它在目标盘上由安装器完成。
- 真实 macOS 启动、安装完成、图形/网络/输入/睡眠。
- 在线 Recovery 在 macOS 26 下能装下 18 GB（Apple 的 5 GB Data 卷限制，上游 #127）。

## 5. 来源等级

- **文档事实**：OpenCore/Apple 文档与源码、Apple 平台安全文档、`bless` 源码、`macrecovery` 源码。
- **社区经验**：EXITBS 的 GPU/kext 类别、CPU 核心数幂次说法；已标注。
- **本项目实测**：Recovery chunklist/首块、完整安装器 URL/Range；见 `recovery/01`、`recovery/03`。
