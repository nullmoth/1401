# Huawei MateBook X Pro 2023 真实硬件扫描

扫描方式：官方 `p1401.scan`（Hardware Sniffer + ACPI dump），只读，非管理员会话也成功完成。原始文件：

- `out/huawei-scan/Report.json`
- `out/huawei-scan/ACPI/`（含 `dsdt.aml`，共 30+ 张表）
- `reports/logs/huawei-scan.log`

> 注：`--run-id` 必须是 32 位十六进制；首次传 `huawei-20261111` 被拒绝，未产生任何写入。

## 1. 机型与固件

| 项 | 值 |
|---|---|
| 厂商/型号 | HUAWEI / **MRGFG-XX** |
| 主板 | HUAWEI **MRGFG-XX-PCB**，Chipset `Raptor Lake-P`，Platform `Laptop` |
| BIOS | 版本 1.17，日期 2026-03-05，x64，**UEFI**，Secure Boot `Disabled`（报告值） |
| 序列号（不写入发布物） | 仅保留在本机 `Report.json`，未在报告中复述 |
| 内存 | 约 32 GB（34,070,585,344 bytes） |

## 2. CPU

| 项 | 值 |
|---|---|
| 名称 | 13th Gen Intel(R) Core(TM) i7-1360P |
| 代号 | **Raptor Lake-P** |
| 核心/线程 | 12 核（4 P + 8 E）/ 16 线程（WMI） |
| 指令集 | SSE…SSE4.2、AVX、AVX2 |
| macOS 兼容判定（上游） | Up to macOS Tahoe 26 |

## 3. GPU 与显示

| 项 | 值 |
|---|---|
| 名称 | Intel(R) Iris(R) Xe Graphics |
| Device ID | **8086-A7A0** |
| Subsystem | 3E6C19E5 |
| 类型 | Integrated GPU |
| PCI Path | `PciRoot(0x0)/Pci(0x2,0x0)` |
| ACPI Path | `\_SB.PC00.GFX0` |
| Resizable BAR | Disabled |
| 内屏 | `CSO1415`（Internal，构建日志） |
| 其他显示设备 | `OrayIddDriver Device`（虚拟显示驱动，非硬件 GPU） |

## 4. 网络与蓝牙

| 设备 | Bus | Device ID | 路径 |
|---|---|---|---|
| Intel Wi-Fi 6E AX211 160MHz | PCI | **8086-51F1** | `PciRoot(0x0)/Pci(0x14,0x3)`，ACPI `\_SB.PC00.CNVW` |
| Realtek USB GbE Family Controller | USB | **0BDA-8153** | RTL8153（USB 以太网） |
| Intel 无线 Bluetooth | USB | **8087-0033** | — |

## 5. 输入设备（关键：TPD0 与 TPL1 必须分开）

| 名称 | Bus | Device | Device Type | 判定 |
|---|---|---|---|---|
| 符合 HID 标准的触摸板 | ACPI | **GXTP786** | I2C HID 设备 | **触摸板** |
| 符合 HID 标准的触摸屏 | ACPI | **GXTP738X** | I2C HID 设备 | **触摸屏，不是触摸板** |
| PS/2 标准键盘 | ACPI | MSFT0001 | PS/2 | 键盘 |
| USB 输入设备 | USB | 12D1-10C8 | — | USB HID（可能为外接/虚拟） |

`GXTP786` 与 `GXTP738X` 是两个独立 ACPI 设备；生成器不应把触摸屏当作 TPD0，也不应把触摸屏的 kext 结果当成触摸板可用。

## 6. USB 控制器

| 名称 | Device ID | PCI Path | ACPI Path |
|---|---|---|---|
| Intel USB 3.10 xHCI | **8086-51ED** | `PciRoot(0x0)/Pci(0x14,0x0)` | `\_SB.PC00.XHCI` |
| Intel USB 3.20 xHCI | **8086-A71E** | `PciRoot(0x0)/Pci(0xd,0x0)` | `\_SB.PC00.TXHC` |
| USB4 Host Router | 8086-A76D | `PciRoot(0x0)/Pci(0xd,0x3)` | `\_SB.PC00.TDM1` |
| USB4 Host Router #1 | 8086-A73E | `PciRoot(0x0)/Pci(0xd,0x2)` | `\_SB.PC00.TDM0` |

## 7. 存储

| Disk | 型号 | Bus | 容量 | 用途 |
|---|---|---|---|---|
| Disk 0 | WD PC SN740 SDDPNQE-2T00-1027 | NVMe | 2,048,408,248,320 | **Windows 系统盘（禁止修改）** |
| Disk 1 | aigo U350 | USB | 125,304,832,000 | 目标安装 U 盘（未写入） |
| Disk 2 | **ACASIS TBU405Pro** | USB | 1,024,209,543,168 | 目标 macOS 安装盘（未修改） |

存储控制器：`15B7-5017`（WD Black SN770 / PC SN740 / PC SN560，NVMe），PCI `PciRoot(0x0)/Pci(0x6,0x0)/Pci(0x0,0x0)`，ACPI `\_SB.PC00.PEG0.PEGP`。

## 8. 音频与其他

- 音频控制器：`8086-51CA`（Intel HDA）。
- 音频设备：`14F1-20D0` 等（INTELAUDIO），另有 USB 音频与蓝牙音频。
- 生物识别：Windows Hello 人脸识别软件设备（macOS 不支持）。
- ACPI：`p1401.scan` 成功导出全部表；`iasl` 预反汇编报告 DSDT 有重复名称（248 个外部方法未解析），构建继续且未使用预补丁反汇编。该警告不阻止 EFI 生成，但列入待实机/后续 ACPI 修复项。

## 9. 与生成器输入的关系

- `Report.json` 的 `Storage Drives` 是 1401 自有段，上游 `check_compatibility()`/验证器会丢弃；本次已让 Huawei 通知从 `res.raw_hardware` 读取该段，外置盘通知因此生效。
- `ACPI/` 用于构建，`dsdt.aml` 存在；`SSDT-*` 由上游规则选择。
- 该扫描是本机真实数据，不是合成样本。
