# 1401-HUAWEI 本地开发说明

本仓库是 [`nullmoth/1401`](https://github.com/nullmoth/1401) 的自有 Fork，面向 **Huawei MateBook X Pro 2023（MRGFG-XX，i7-1360P，Iris Xe A7A0，AX211）** 做硬件适配、Bug 修复与可复现构建。

- 基线：官方 `v2.9` = `03c79ef772f6142d59eb5203ce0efa98845bd0ba`（与官方 Release `v2.9` 的 `target_commitish` 一致）。
- 本 Fork 版本：**2.9.1**（Windows 应用 `App.csproj`/`app.manifest`）。
- 远端：
  - `origin` = `https://github.com/a137460387/1401.git`（自有 Fork）
  - `upstream` = `https://github.com/nullmoth/1401.git`（官方）
- 本 Fork 不向上游提交 PR/Issue；上游贡献规则见 `AGENTS.md`/`CONTRIBUTING.md`。

## 分支模型

| 分支 | 用途 |
|---|---|
| `main` | 稳定发布分支；只在完整回归通过后从 `develop` 合并 |
| `develop` | 日常集成；所有 fix/feature 合并到这里 |
| `fix/*` | 单个 Bug 修复，独立提交/测试 |
| `feature/huawei-1401` | MateBook 专属适配；不把 Huawei 规则混入通用核心 |
| `release/*` | 稳定版本发布准备 |

已有修复分支：`fix/usb-erase-identity`、`fix/windows-write-safety`、`fix/full-installer-download`、`fix/recovery-pre-erase-verification`、`fix/dependency-cache-recovery`；特性分支：`feature/huawei-1401`。

## 构建

```powershell
# 项目内 .NET SDK 8.0.425（一次性；不改系统 PATH）
powershell -ExecutionPolicy Bypass -File .dotnet-setup\dotnet-install.ps1 -Version 8.0.425 -InstallDir .dotnet -NoPath
# Python 环境（一次性）
py -3.12 -m venv .venv
.\.venv\Scripts\pip install pywin32==312 WMI==1.5.1 certifi truststore
# 构建
.\.dotnet\dotnet.exe build windows\App\App.csproj -c Release -o build\1401-compiled-291 -p:ContinuousIntegrationBuild=true
```

## 测试

```powershell
scripts\run-tests.cmd          # 全量；自动加载 MSVC 环境
.\.venv\Scripts\python.exe -m p1401.apple --selftest
.\.venv\Scripts\python.exe -m p1401.usbwriter --selftest
.\.venv\Scripts\python.exe -m p1401.nullmoth --selftest
```

真实硬件扫描（只读）：

```powershell
.\.venv\Scripts\python.exe -m p1401.scan out\huawei-scan
```

生成 EFI（写项目目录，不写真实盘）：

```powershell
.\.venv\Scripts\python.exe -m p1401 build out\huawei-scan\Report.json out\huawei-scan\ACPI out\huawei-efi --macos 25 --json
```

> macOS 26 Tahoe 的 Darwin 主版本是 **25**。`--macos 26` 会被引擎拒绝（Darwin 26 不存在）。

验证：

```powershell
.\.venv\Scripts\python.exe scripts\verify_efi.py out\huawei-efi --json-out reports\hardware\efi-file-check.json
.\.venv\Scripts\python.exe scripts\verify_recovery.py --json-out reports\recovery\verification.json
```

## 安全边界

- **永远不要**在未授权时运行真实写盘：`p1401.usbwriter write` 会整盘擦除目标 U 盘（MBR + active FAT32）。
- **WD SN740 2TB 系统盘永远禁止修改**。
- aigo U350、ACASIS TBU405Pro 的真实写盘/格式化/部署 EFI 需用户单独明确授权。
- EFI 只生成到项目 `out/` 目录；文件级检查不等于可启动验证。
- 所有报告区分“本机实测 / 源码验证 / 文档上游 / 待实机验证”，见 `reports/`。

## 上游同步

见 `reports/releases/02-回滚与上游同步.md` 与 `scripts/sync-upstream.sh`。原则：先 fetch、记录变更、在集成分支 merge（不 rebase 覆盖历史）、跑全量测试、保留自有补丁、只 fast-forward/merge、绝不 force push。

## 关键新增

- `p1401/huawei.py`：MateBook 专属通知（A7A0/WhateverXe、AX211/itlwm、GXTP786 触摸板 vs GXTP738X 触摸屏、TBU405Pro 外置盘）。
- `p1401/machine_recipes.json`：Huawei CPUID/拓扑配方（状态 `theory`，未实机启动）。
- `p1401/netsupport.py`：itlwm 不再被当作安装器可联网。
- `p1401/utbmap.py::map_status`：报告“有 map / 默认无 map / 无 USB 栈”。
- 擦盘身份复核、参数引用、大容量盘确认、#161 修复、Recovery 擦盘前校验、缓存回退、Windows UI 安全默认值。
- `scripts/verify_efi.py`、`scripts/verify_recovery.py`、`scripts/run-tests.cmd`、`scripts/sync-upstream.sh`。
