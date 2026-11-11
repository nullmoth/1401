# Release 2.9.1（Huawei Fork）说明

- **版本**：2.9.1（Windows 应用 `AssemblyVersion/FileVersion` 2.9.1.0）
- **基线**：官方 `nullmoth/1401` v2.9 = `03c79ef772f6142d59eb5203ce0efa98845bd0ba`
- **标签**：`v2.9.1-huawei.1`（指向发布提交 `f64286e`）
- **Release**：<https://github.com/a137460387/1401/releases/tag/v2.9.1-huawei.1>
- **日期**：2026-11-11
- **性质**：自有 Fork 的稳定开发版本；面向 Huawei MateBook X Pro 2023（MRGFG-XX，i7-1360P，Iris Xe A7A0，AX211）

## 1. 主要变更

### 安全（擦盘路径）
- 擦除前在**打开的物理盘句柄**上复核序列号/型号/容量；不匹配拒绝，且在删除分区表之前。
- `current_number()` 无法唯一重识别时返回 `None`；diskpart 回退不再猜测旧磁盘号。
- 格式脚本不再回退旧号；完整安装器第二分区使用写盘最终磁盘号。
- Windows 参数按 `CommandLineToArgvW` 规则引用，防止 `\` 结尾路径吞掉 `--stick-id` 等参数。
- >256 GiB USB 盘需要独立确认（默认“否”），不再自动 `--allow-large`。
- WMI 回退在系统盘号未知时 fail-closed。

### Recovery 与完整安装器
- #161：完整安装器下载按目录大小封顶；超大 `.part` 重下；416/非瞬态 4xx 终止；流必关。
- 本地 `BaseSystem.dmg` 在擦盘前完整校验（签名 chunklist、大小、逐块 SHA-256）。
- 在线预检改为哈希完整首块（≤64 MiB）。
- 完整镜像与 chunklist fsync；本地复制逐块重试。
- 真实验证：Apple Recovery 960,530,321 B / 92 块全部通过，读回 0 差异；完整安装器目录 26.7.3/25G342/18,388,869,343 B，真实 URL Range 206。

### 构建可靠性
- 依赖缓存子目录 ACL 拒绝写入时回退 `OCK_Files-2/-3`。
- 校验使用实际构建缓存的 OpenCore 版本，修复 x570 语料的假失败。
- 打包检查的 `--output` 归一化为绝对路径（`cl /OUT` 相对 cwd 的坑）。

### Huawei 适配
- 新 `p1401/huawei.py`：A7A0/WhateverXe、AX211/itlwm+HeliPort、GXTP786 触摸板 vs GXTP738X 触摸屏、TBU405Pro 外置盘。
- `machine_recipes.json`：`ProvideCurrentCpuInfo + CPUID 128`，状态 `theory`（同 CPU 的 XPS 9320 已验证，本板未启动）。
- itlwm 不再算作安装器可联网；AX211 机型提示以太网/完整离线安装器。
- `utbmap.map_status()` 报告默认无 map。
- Intel Xe 通知与真实 EFI 一致。

### 文档/测试
- 修正 `EXITBS:START`/`OS.dmg.root_hash` 的错误因果描述。
- 修正 ocvalidate 4551 回退、Python 3.13、2 GB 最小盘、`build-log.txt` 等过时说明。
- 测试：**1190 项，0 失败，8 项环境/可选依赖跳过**。

## 2. 构建产物

| 文件 | SHA-256 |
|---|---|
| `out/release-artifact/1401-Windows-2.9.1.zip` | `e4a8bfba7f1f4b0238e54374386e96786a51fcbd160ff4a0a947cb6c8302f9f9`（95,383,699 bytes） |
| `out/huawei-efi-release/EFI/OC/config.plist` | `f1b65f6bceac80c1d3f986d898664746ecc36e3cab2ec1d31b536a83f7865bc5` |
| `out/huawei-efi-release/EFI/OC/OpenCore.efi` | `5af6acdaabdf02f8727fd3ee2aac3ae8388f4059ce939970e167a503d12aa82a` |

同一目录另有 `SHA256SUMS.txt` 与 `windows-verification.json`（`ok=true`，版本 2.9.1，打包回归 1214 项 0 失败 0 跳过）。

## 3. 验证状态

| 项 | 状态 |
|---|---|
| Windows Release 构建 | 成功，0 warning/0 error |
| Python 全量测试 | 1190 项，0 失败，8 跳过 |
| 官方 corpus（x570 + optiplex） | 2/2 OK，ocvalidate 0 问题 |
| 真实 MateBook EFI 生成 | ok=true，23 kext 名称/30 条目，11 ACPI，5 驱动 |
| EFI `ocvalidate` | 0 问题 |
| EFI 文件级检查 | ok=true，错误 0 |
| Recovery 完整镜像 | 960,530,321 B，92/92 块，读回 0 差异 |
| 完整安装器目录/URL/Range | 已验证；18 GB 未下载 |
| 打包运行时验证 | **通过**：ok=true，2.9.1，回归 1214 项 0 失败 0 跳过，GUI 自检通过 |
| 真实 macOS 启动/安装 | **未验证**（需授权写盘+重启） |

## 4. 华为硬件结论（摘要）

| 硬件 | 结论 | 等级 |
|---|---|---|
| i7-1360P / Raptor Lake-P | 识别、SMBIOS MacBookPro16,2、混合核心规则 | 源码+真实构建 |
| Iris Xe A7A0 | 生成器选中 WhateverXe；加速包 opt-in | 文件级；加速待实机 |
| AX211 | itlwm + HeliPort；安装器需以太网/完整安装器 | 源码+真实构建 |
| GXTP786 触摸板 | VoodooI2C/HID + VoodooPS2 + `-vi2c-force-polling` | 文件级；待实机 |
| GXTP738X 触摸屏 | macOS 无驱动，明确不承诺 | 扫描实测 |
| TBU405Pro 外置盘 | 标记外置、非安装目标；需 APFS + U 盘 OpenCore | Windows 识别；macOS 待实机 |
| USB 端口映射 | 使用 UTBDefault，**无 UTBMap**；构建明确提示 | 文件级；睡眠/端口待实机 |

## 5. 已知限制

- 未写真实 U 盘、未部署 EFI、未重启、未安装 macOS。
- WhateverXe 图形加速、AX211 Wi-Fi、触摸板手势、外置盘 UASP/睡眠唤醒未验证。
- 完整安装器 18 GB 未实际下载；标准 `createinstallmedia` 盘需 macOS。
- `OS.dmg.root_hash` 是目标盘 Preboot/SSV 产物，不由 1401 生成或修复。
- 在线 Recovery 在 macOS 26 的 5 GB Data 卷限制仍存在（上游 #127）。

## 6. 使用

1. 解压发布包，保持 `1401` 文件夹完整。
2. 以管理员运行 `1401.exe`。
3. Check this PC → Build the Mac setup → 按 BIOS 步骤 → Create the macOS stick。
4. 目标机为 Huawei MateBook X Pro 2023 时，构建会显示 Huawei 专属通知；AX211 机型建议接以太网或使用完整离线安装器。
5. 写盘会整盘擦除所选 U 盘；本项目未对 aigo U350/ACASIS TBU405Pro 执行写盘。

## 7. 许可

继承上游：PolyForm Noncommercial 1.0.0；第三方组件各自许可见 `NOTICE.md`。NullMoth 名称与标志不随许可授予。
