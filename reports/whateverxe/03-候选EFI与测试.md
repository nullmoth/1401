# 03 独立 Huawei EFI 候选与验证

## 1. 生成命令

```powershell
.\.venv\Scripts\python.exe -m p1401 build `
  out\huawei-scan\Report.json out\huawei-scan\ACPI out\huawei-efi-whateverxe-audit `
  --macos 25 --json
```

- 输入是真实 MateBook 扫描：`out/huawei-scan/Report.json` + `out/huawei-scan/ACPI/`。
- `--macos 25` 是 Darwin 主版本 25（macOS 26 Tahoe）；不是 `--macos 26`。构建结果
  `macos_version=25.99.99`。
- 输出目录是新的 `out/huawei-efi-whateverxe-audit/`，没有覆盖、移动或删除 `out/huawei-efi-release/`，
  没有触碰 `v2.9.1-huawei.1` 标签或 GitHub Release 资产。
- 构建结果：`ok=true`，`smbios=MacBookPro16,2`，`needs_oclp=false`。

## 2. 候选 EFI 的 WhateverXe 事实

路径：`out/huawei-efi-whateverxe-audit/EFI/OC/config.plist`

| 项目 | 实际值 |
|---|---|
| `WhateverXe.kext` | `org.b00t0x.WhateverXe`，`CFBundleVersion=0.8.0`，Enabled |
| `WhateverXe.MinKernel` | `25.7.0` |
| `AMFIPass.kext` | `com.dhinakg.AMFIPass`，`1.4.1`，Enabled |
| AMFIPass 二进制 SHA-256 | `2d36aeca1740b258e6bb0b66844b5bfb59a0edb7cdd9ef78206689e5d223d8dc` |
| `Lilu.kext` | `1.7.3`，Enabled，索引 0 |
| `WhateverGreen.kext` | 不存在 |
| `csr-active-config` | `0x00000A03`（含 `0x803` 的 `0x800` 位） |
| `boot-args` | `-v debug=0x100 keepsyms=1 -allow3d -disablegfxfirmware -igfxdvmt -vi2c-force-polling ctrsmt=full -ibtcompatbeta revpatch=sbvmm` |
| iGPU `DeviceProperties` | `framebuffer-patch-enable=01000000`，`framebuffer-stolenmem=0000C003` |
| `SSDT-PNLF.aml` | 存在且 Enabled |
| `Kernel/Add` 条目 | 30 |
| `ACPI/Add` 条目 | 11 |
| UEFI 驱动 | 5 |

### 2.1 WEX 下载与 SHA-256 校验

候选构建的 JSON 上下文（`out/huawei-efi-whateverxe-audit-build.json`）记录了：

```text
Updating WhateverXe...
from https://github.com/b00t0x/WhateverXe/releases/download/0.8.0/WhateverXe-0.8.0-RELEASE.zip
Verifying SHA256 checksum...
Checksum verified successfully.
Updating AMFIPass-b00t0x...
from https://github.com/b00t0x/WhateverXe-Graphics/raw/88d64a.../extras/AMFIPass-v1.4.1-Mod-RELEASE.zip
Verifying SHA256 checksum...
Checksum verified successfully.
```

这与 `p1401/whateverxe.py` 的固定值一致：

- WEX ZIP SHA-256 `5b71e14ce10c673f6baba276183f268d7f04766d298cd34f1df0bb96f11c8e4b`；
- AMFIPass Mod ZIP SHA-256 `71f41de42e355d2a83e6f093ef34a5b24d0a9c9a9085830b2317f1b874f56250`。

## 3. 文件级验证

命令：

```powershell
.\.venv\Scripts\python.exe scripts\verify_efi.py out\huawei-efi-whateverxe-audit `
  --json-out reports\hardware\efi-file-check-whateverxe-audit.json
```

结果：`ok=true`，`errors=[]`，82 项检查全部通过。关键项：

| 检查 | 结果 |
|---|---|
| `WhateverXe is enabled` | true |
| `WhateverXe Tahoe MinKernel is 25.7.0` | true |
| `Lilu is enabled before WhateverXe` | true |
| `WhateverXe has AMFIPass enabled` | true |
| `WhateverGreen is off with WhateverXe` | true |
| `WhateverXe boot-arg -allow3d` | true |
| `WhateverXe boot-arg -disablegfxfirmware` | true |
| `WhateverXe SIP includes 0x803` | true（实际 `0x0A03`） |
| `WhateverXe bundle is pinned 0.8.0` | true（`0.8.0`） |
| `OpenCore ocvalidate` | true，0 issues |

`ocvalidate` 输出：

```text
NOTE: This version of ocvalidate is only compatible with OpenCore version 1.0.9!
Completed validating config.plist in 1 ms. No issues found.
```

### 3.1 校验和

| 文件 | SHA-256 |
|---|---|
| `EFI/OC/config.plist` | `c70105907a6fb5fc11d2efc1a136876d8ba6fa348b0d253143412c72df3b83c3` |
| `EFI/OC/OpenCore.efi` | `5af6acdaabdf02f8727fd3ee2aac3ae8388f4059ce939970e167a503d12aa82a` |

完整报告：`reports/hardware/efi-file-check-whateverxe-audit.json`。

## 4. 与 2.9.1 示例 EFI 的差异

对两份 `config.plist` 做递归比较，差异只有：

| 键 | 2.9.1 示例 | 候选 |
|---|---|---|
| `NVRAM.Add.7C436110-…csr-active-config` | `03 00 00 00`（`0x03`） | `03 0A 00 00`（`0x0A03`） |
| `PlatformInfo.Generic.MLB` | `<已打码>` | `<已打码>` |
| `PlatformInfo.Generic.ROM` | `<已打码>` | `<已打码>` |
| `PlatformInfo.Generic.SystemSerialNumber` | `<已打码>` | `<已打码>` |
| `PlatformInfo.Generic.SystemUUID` | `<已打码>` | `<已打码>` |

- `csr-active-config` 是本次修复的预期差异。
- 四个 SMBIOS 身份字段（MLB、ROM、SystemSerialNumber、SystemUUID）的实际值已打码：仓库公开，这些值一旦被用于
  真机就会成为该机器的 Apple 身份。打码前的值仍在 Git 历史中，真机使用前请重新生成 SMBIOS，不要沿用这里出现过的值。
- 身份字段不同是因为候选 EFI 在新目录中重新生成了 SMBIOS；候选是独立交付物，不是覆盖发布 EFI 的补丁。
  如果用户希望沿用已安装系统的序列号，应在自己的输出目录上重建，或把旧身份复制到候选；本次不自动做这件事。

## 5. 自动化测试结果

### 5.1 Python 全量套件

```powershell
cmd /c scripts\run-tests.cmd
```

结果：

```text
Ran 1228 tests in 84.151s

OK
```

（包含新增的 `tests/test_whateverxe_integration.py` 14 项。）

### 5.2 策略自检

```powershell
.venv\Scripts\python.exe -m p1401.selftest
```

结果：`51/51 passed`。其中新增/修改的检查：

- 没有 VoodooHDA 时，Tahoe 构建保持 SIP 全开（音频菜单答案本身不再降低 SIP）；
- 真正启用 `VoodooHDA.kext` 时才降到 `0x03`。

### 5.3 Mac setup 的 WhateverXe 测试

```powershell
.venv\Scripts\python.exe mac\tools\test_xe_whateverxe.py
```

结果：`Ran 14 tests ... OK`。新增用例：

- `test_second_run_with_whateverxe_loaded_raises_sip_before_the_package`
  —— WEX 已加载、SIP=0x03 时，先抬到 0x803、要求重启、**不**安装 Graphics；
- `test_second_run_after_the_sip_fix_installs_the_graphics_package`
  —— 重启后的下一次运行才安装；
- `test_second_run_with_compliant_sip_installs_the_graphics_package`
  —— SIP 已含 0x803 时直接安装。

该测试在 Windows 上通过 Python `plutil`/`ditto`/`base64` 兼容垫片运行；在 macOS 上仍使用系统自带的
`plutil`、`ditto`、`base64`。

### 5.4 新增测试覆盖的规则

`tests/test_whateverxe_integration.py`：

- Windows pin 与 Mac setup 的 WEX / AMFIPass Mod / Graphics URL+SHA-256 完全一致；
- OpCore 实际拿到的 `WhateverXe.download_info` 与 `AMFIPassModDownloadInfo` 是固定值；
- WEX + `csr=0x03` → 最终含 `0x803`；
- WEX + `csr=0x0A43` → 保留 `0x0A43`；
- WEX + WhateverGreen → WhateverGreen 关闭；
- WEX 缺 boot-args → 补齐；
- Tahoe 构建 WEX `MinKernel=25.7.0`，Sequoia 构建不改；
- 没有 WEX 时不添加 WEX 参数；
- 音频菜单 prompt 本身不降 SIP，真正的 VoodooHDA kext 才降。

## 6. 复现性

- WEX、AMFIPass Mod、Graphics 的 URL/SHA-256 固定在 `p1401/whateverxe.py`。
- `mac/Resources/nullmoth-setup.sh` 的 Mac 端 pin 与 `p1401/whateverxe.py` 由测试强制一致。
- OpCore 下载器对非空 `sha256` 做校验；候选构建日志已显示两次 `Checksum verified successfully`。
- 其余 kext 仍按上游 OpCore 的 release 选择逻辑；本次没有把整个 kext 集固定成 manifest，这是 1401 既有设计，
  不在 WhateverXe 专项范围内。

## 7. 使用边界

- 候选 EFI 只用于文件级审查和后续实机测试；本审计没有把它写入任何 U 盘或 EFI 分区。
- 候选 EFI 不是 2.9.1 正式发布资产，不要用它替换 `v2.9.1-huawei.1` 的发布包。
- 实机测试前先读 `04-风险与未验证.md`。
