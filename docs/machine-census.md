# Field machine census

4611 distinct PCs (8097 reporting machines) from Check this PC receipts and build logs, 2026-10-22 to 2026-11-07. Device IDs only. Each device's resolution is measured by replaying a baseline PC with and without it through the real builder (tools/machine_census.py), for macOS 15; macOS 26 differs only where noted.

## CPU

Intel Alder Lake-S 760, Intel Alder Lake-H 719, Intel Raptor Lake-S 611, Intel Raptor Lake-HX 572, Intel Comet Lake-S 322, Intel Coffee Lake-S 292, AMD Vermeer 254, Intel Raptor Lake-H 213, AMD Raphael 205, Intel Coffee Lake-U 193, Intel Haswell 192, Intel Tiger Lake-H 177, AMD Granite Ridge 170, AMD Cezanne 165, Intel Arrow Lake-HX 164, AMD Barcelo-R 159, AMD Rembrandt-R 156, Intel Ivy Bridge 148, Intel Coffee Lake-H 136, Intel Unknown 134, Intel Haswell-EP 132, Intel Comet Lake-H 130, Intel Tiger Lake-UP3 129, AMD Dragon Range 116, Intel Kaby Lake 113, Intel Skylake 113, AMD Phoenix 92, Intel Rocket Lake-S 87, AMD Renoir 86, AMD Matisse 85, ...

## GPU

479 distinct devices. PCs by outcome: native or none needed 9342, kext 1896, stops the build 88.

| devices with no driver or that stop the build | PCs | device ID | outcome |
|---|---|---|---|
| Podstawowa karta graficzna Microsoft | 37 | 15AD-0405 | stops the build |
| Microsoft Basic Display Adapter | 23 | 1AE0-A001 | stops the build |
| Microsoft Temel Görüntü Bağdaştırıcısı | 9 | 1B36-0100 | stops the build |
| ZX C-960 | 5 | 1D17-3A04 | stops the build |
| Microsoft 基本显示适配器 | 4 | 1234-1111 | stops the build |
| Parallels Display Adapter (WDDM) | 2 | 1AB8-4005 | stops the build |
| Innosilicon Technologies Fantasy G Series | 2 | 1EC8-9810 | stops the build |
| Red Hat VirtIO GPU DOD controller | 2 | 1AF4-1050 | stops the build |
| Microsoft 基本显示适配器 | 2 | 1A03-2000 | stops the build |
| Citrix Indirect Display Adapter | 2 | 5853-1003 | stops the build |

## Network

325 distinct devices. PCs by outcome: kext 8051, native or none needed 5617, no driver (switched off, noted) 818.

| devices with no driver or that stop the build | PCs | device ID | outcome |
|---|---|---|---|
| Intel(R) Wi-Fi 7 BE200 320MHz | 95 | 8086-272B | no driver (switched off, noted) |
| Qualcomm Atheros QCA61x4A Wireless Network Adapter | 74 | 168C-003E | no driver (switched off, noted) |
| Intel(R) Wi-Fi 7 BE201 320MHz | 70 | 8086-7740 | no driver (switched off, noted) |
| MediaTek Wi-Fi 6 MT7902LEN Wireless LAN Card | 54 | 14C3-7902 | no driver (switched off, noted) |
| Motorcomm YT6801 Gigabit Ethernet Adapter | 47 | 1F0A-6801 | no driver (switched off, noted) |
| Intel(R) 82574L Gigabit Network Connection | 43 | 8086-10D3 | no driver (switched off, noted) |
| Qualcomm Atheros AR956x Wireless Network Adapter | 40 | 168C-0036 | no driver (switched off, noted) |
| Qualcomm FastConnect 7800 Wi-Fi 7 High Band Simultaneous (HB | 33 | 17CB-1107 | no driver (switched off, noted) |
| Qualcomm QCA9377 802.11ac Wireless Adapter | 32 | 168C-0042 | no driver (switched off, noted) |
| Red Hat VirtIO Ethernet Adapter #2 | 27 | 1AF4-1000 | no driver (switched off, noted) |
| Qualcomm FastConnect 6900 Wi-Fi 6E Dual Band Simultaneous (D | 22 | 17CB-1103 | no driver (switched off, noted) |
| Qualcomm Atheros AR946x Wireless Network Adapter | 18 | 168C-0034 | no driver (switched off, noted) |
| MediaTek Wi-Fi 6 MT7920 Wireless LAN Card | 16 | 14C3-7920 | no driver (switched off, noted) |
| Broadcom 802.11g Network Adapter | 15 | 14E4-4315 | no driver (switched off, noted) |
| Realtek RTL8723BE Wireless LAN 802.11n PCI-E NIC | 15 | 10EC-B723 | no driver (switched off, noted) |
| Adattatore per schede Half Mini PCI Express Wireless LAN 11b | 15 | 14E4-4727 | no driver (switched off, noted) |
| Intel(R) Ethernet Connection (24) I219-V | 15 | 8086-57A1 | no driver (switched off, noted) |
| Intel(R) 82567LM Gigabit Network Connection | 14 | 8086-10F5 | no driver (switched off, noted) |
| Qualcomm Atheros AR9485 Wireless Network Adapter | 11 | 168C-0032 | no driver (switched off, noted) |
| Realtek 8821AE Wireless LAN 802.11ac PCI-E NIC | 11 | 10EC-8821 | no driver (switched off, noted) |
| Broadcom 802.11n Network Adapter | 9 | 14E4-4365 | no driver (switched off, noted) |
| MediaTek Wi-Fi 7 MT7927 Wireless LAN Card | 9 | 14C3-7927 | no driver (switched off, noted) |
| Intel(R) PRO/1000 MT Network Connection | 8 | 8086-100E | no driver (switched off, noted) |
| Broadcom NetLink (TM) Gigabit Ethernet | 7 | 14E4-1698 | no driver (switched off, noted) |
| Intel(R) Ethernet Connection (24) I219-LM | 7 | 8086-57A0 | no driver (switched off, noted) |

## Sound

666 distinct devices. PCs by outcome: native or none needed 16205, no driver (switched off, noted) 6128.

| devices with no driver or that stop the build | PCs | device ID | outcome |
|---|---|---|---|
| NVIDIA High Definition Audio | 826 | 10DE-00A7 | no driver (switched off, noted) |
| NVIDIA High Definition Audio | 673 | 10DE-00AD | no driver (switched off, noted) |
| NVIDIA High Definition Audio | 639 | 10DE-009F | no driver (switched off, noted) |
| NVIDIA High Definition Audio | 521 | 10DE-00A0 | no driver (switched off, noted) |
| NVIDIA High Definition Audio | 459 | 10DE-009E | no driver (switched off, noted) |
| NVIDIA High Definition Audio | 268 | 10DE-0093 | no driver (switched off, noted) |
| NVIDIA High Definition Audio | 249 | 10DE-00A6 | no driver (switched off, noted) |
| NVIDIA High Definition Audio | 215 | 10DE-0099 | no driver (switched off, noted) |
| Senary Audio | 194 | 14F1-1F87 | no driver (switched off, noted) |
| NVIDIA High Definition Audio | 180 | 10DE-00A5 | no driver (switched off, noted) |
| NVIDIA High Definition Audio | 178 | 10DE-0080 | no driver (switched off, noted) |
| NVIDIA High Definition Audio | 169 | 10DE-0084 | no driver (switched off, noted) |
| NVIDIA High Definition Audio | 168 | 10DE-0094 | no driver (switched off, noted) |
| AMD Audio Device | 167 | 1022-15E2 | no driver (switched off, noted) |
| NVIDIA High Definition Audio | 146 | 10DE-00AF | no driver (switched off, noted) |
| NVIDIA High Definition Audio | 119 | 10DE-0083 | no driver (switched off, noted) |
| NVIDIA High Definition Audio | 119 | 10DE-009A | no driver (switched off, noted) |
| NVIDIA High Definition Audio | 100 | 10DE-0092 | no driver (switched off, noted) |
| NVIDIA High Definition Audio | 97 | 10DE-0051 | no driver (switched off, noted) |
| NVIDIA High Definition Audio | 92 | 10DE-00AB | no driver (switched off, noted) |
| NVIDIA High Definition Audio | 52 | 10DE-00A4 | no driver (switched off, noted) |
| NVIDIA High Definition Audio | 45 | 10DE-0072 | no driver (switched off, noted) |
| NVIDIA High Definition Audio | 43 | 10DE-00AE | no driver (switched off, noted) |
| NVIDIA High Definition Audio | 43 | 10DE-0060 | no driver (switched off, noted) |
| Urządzenie zgodne ze standardem High Definition Audio | 34 | 15AD-1975 | no driver (switched off, noted) |

## Bluetooth

223 distinct devices. PCs by outcome: kext 5115, no driver (switched off, noted) 1053, native or none needed 277.

| devices with no driver or that stop the build | PCs | device ID | outcome |
|---|---|---|---|
| 英特尔(R) 无线 Bluetooth(R) | 64 | 8087-0037 | no driver (switched off, noted) |
| MediaTek Bluetooth Adapter | 61 | 0489-E111 | no driver (switched off, noted) |
| Realtek Bluetooth Adapter | 55 | 0BDA-5852 | no driver (switched off, noted) |
| Generic Bluetooth Adapter | 44 | 10D7-B012 | no driver (switched off, noted) |
| RZ616 Bluetooth(R) Adapter | 43 | 0489-E0D8 | no driver (switched off, noted) |
| MediaTek Bluetooth Adapter | 42 | 13D3-3596 | no driver (switched off, noted) |
| Realtek Bluetooth Adapter | 40 | 0BDA-C821 | no driver (switched off, noted) |
| Generic Bluetooth Adapter | 33 | A69C-8D81 | no driver (switched off, noted) |
| MediaTek Bluetooth Adapter | 31 | 13D3-3602 | no driver (switched off, noted) |
| Qualcomm Atheros QCA61x4 Bluetooth | 28 | 0CF3-E300 | no driver (switched off, noted) |
| Qualcomm QCA61x4A Bluetooth | 28 | 0CF3-E007 | no driver (switched off, noted) |
| Realtek Bluetooth Adapter | 28 | 0BDA-0852 | no driver (switched off, noted) |
| BARROT Bluetooth Adapter | 26 | 33FA-0001 | no driver (switched off, noted) |
| BARROT Bluetooth 5.4 Adapter | 21 | 33FA-0010 | no driver (switched off, noted) |
| BARROT Bluetooth 6.0 Adapter | 20 | 33FA-0012 | no driver (switched off, noted) |
| Realtek Bluetooth Adapter | 17 | 0BDA-D922 | no driver (switched off, noted) |
| MediaTek Bluetooth Adapter | 16 | 04CA-3804 | no driver (switched off, noted) |
| Qualcomm QCA9377 Bluetooth | 13 | 0CF3-E009 | no driver (switched off, noted) |
| Generic Bluetooth Adapter | 13 | 368B-8D81 | no driver (switched off, noted) |
| Realtek Bluetooth 4.0 Adapter | 12 | 0BDA-B728 | no driver (switched off, noted) |
| Realtek Bluetooth Adapter | 12 | 13D3-3558 | no driver (switched off, noted) |
| Realtek Bluetooth Adapter | 11 | 0BDA-C820 | no driver (switched off, noted) |
| Realtek Bluetooth Adapter | 11 | 0BDA-B023 | no driver (switched off, noted) |
| Generic Bluetooth Adapter | 10 | 0BDA-C761 | no driver (switched off, noted) |
| MediaTek Bluetooth Adapter | 10 | 0489-E139 | no driver (switched off, noted) |

## Storage Controllers

415 distinct devices. PCs by outcome: native or none needed 11900, stops the build 2260, kext 574, no driver (switched off, noted) 242.

| devices with no driver or that stop the build | PCs | device ID | outcome |
|---|---|---|---|
| RST VMD Managed Controller | 894 | 8086-09AB | stops the build |
| Volume Management Device NVMe RAID Controller | 878 | 8086-467F | stops the build |
| Volume Management Device NVMe RAID Controller Intel Corporat | 292 | 8086-A77F | stops the build |
| Volume Management Device NVMe RAID Controller | 87 | 8086-9A0B | stops the build |
| Volume Management Device NVMe RAID Controller Intel Corporat | 83 | 8086-AD0B | stops the build |
| PC611 NVMe Solid State Drive | 70 | 1C5C-1639 | no driver (switched off, noted) |
| 2200S NVMe SSD [Cassandra] | 64 | 1344-5410 | no driver (switched off, noted) |
| PC601 NVMe Solid State Drive | 33 | 1C5C-1627 | no driver (switched off, noted) |
| Optane NVME SSD H10 with Solid State Storage [Teton Glacier] | 32 | 8086-0975 | no driver (switched off, noted) |
| NVMe Optane Memory Series | 23 | 8086-2522 | no driver (switched off, noted) |
| Volume Management Device NVMe RAID Controller Intel Corporat | 21 | 8086-7D0B | stops the build |
| Optane NVME SSD H20 with Solid State Storage [Pyramid Glacie | 20 | 8086-09AD | no driver (switched off, noted) |
| Volume Management Device NVMe RAID Controller | 3 | 8086-201D | stops the build |
| Intel(R) RST VMD Managed Controller B07F | 1 | 8086-B07F | stops the build |
| Intel(R) RST VMD Controller B06F | 1 | 8086-B06F | stops the build |

## USB Controllers

216 distinct devices. PCs by outcome: native or none needed 17753.

## SD Controller

59 distinct devices. PCs by outcome: kext 789, no driver (switched off, noted) 385, native or none needed 50.

| devices with no driver or that stop the build | PCs | device ID | outcome |
|---|---|---|---|
| SDA Standard Compliant SD Host Controller | 70 | 17A0-9755 | no driver (switched off, noted) |
| SDA Standard Compliant SD Host Controller | 40 | 1217-8621 | no driver (switched off, noted) |
| Genesys Logic PCIE card reader device | 37 | 17A0-9750 | no driver (switched off, noted) |
| JMicron PCIe SD Host Controller | 21 | 197B-2381 | no driver (switched off, noted) |
| SDA Standard Compliant SD Host Controller | 21 | 1217-8520 | no driver (switched off, noted) |
| Realtek PCIE CardReader | 17 | 10EC-5261 | no driver (switched off, noted) |
| SDA Standard Compliant SD Host Controller | 15 | 1180-0822 | no driver (switched off, noted) |
| JMicron PCIe xD Host Controller | 15 | 197B-2384 | no driver (switched off, noted) |
| JMicron PCIe SD/MMC Host Controller | 15 | 197B-2382 | no driver (switched off, noted) |
| JMicron PCIe MS Host Controller | 15 | 197B-2383 | no driver (switched off, noted) |
| Controller host SD compatibile standard SDA | 14 | 14E4-16BC | no driver (switched off, noted) |
| Contrôleur hôte numérique sécurisé Intel | 11 | 8086-A375 | no driver (switched off, noted) |
| SDA Standard Compliant SD Host Controller | 10 | 197B-2391 | no driver (switched off, noted) |
| Realtek PCIE CardReader | 10 | 10EC-5228 | no driver (switched off, noted) |
| Intel SD 主控制器 | 9 | 8086-9D2B | no driver (switched off, noted) |
| Realtek PCIE CardReader | 8 | 10EC-5264 | no driver (switched off, noted) |
| Alcorlink PCIE Card Reader | 7 | 1AEA-6625 | no driver (switched off, noted) |
| Genesys Logic PCIE card reader device | 6 | 17A0-9767 | no driver (switched off, noted) |
| Intel SD 主控制器 | 5 | 8086-06F5 | no driver (switched off, noted) |
| SDA Standard Compliant SD Host Controller | 3 | 1217-8320 | no driver (switched off, noted) |
| Intel SD 主控制器 | 3 | 8086-02F5 | no driver (switched off, noted) |
| Intel SD 主控制器 | 3 | 8086-31CC | no driver (switched off, noted) |
| Intel SD 主控制器 | 3 | 8086-34F8 | no driver (switched off, noted) |
| SDA Standard Compliant SD Host Controller | 2 | 1217-9863 | no driver (switched off, noted) |
| Realtek PCIE CardReader | 2 | 10EC-5250 | no driver (switched off, noted) |

## Biometric

106 distinct devices. PCs by outcome: no driver (switched off, noted) 1514.

| devices with no driver or that stop the build | PCs | device ID | outcome |
|---|---|---|---|
| Facial Recognition (Windows Hello) Software Device | 801 | name:Facial Recognition (Windows Hello) Software Device | no driver (switched off, noted) |
| Windows Hello Face Software Device | 89 | name:Windows Hello Face Software Device | no driver (switched off, noted) |
| FocalTech Fingerprint Reader | 46 | 2808-A658 | no driver (switched off, noted) |
| Synaptics UWP WBDI | 36 | 06CB-00BD | no driver (switched off, noted) |
| Synaptics FP Sensors (WBF) (PID=0017) | 29 | 138A-0017 | no driver (switched off, noted) |
| ELAN WBF Fingerprint Sensor | 24 | 04F3-0C4B | no driver (switched off, noted) |
| FPC Fingerprint Reader (Disum) | 23 | 10A5-9201 | no driver (switched off, noted) |
| Goodix MOC Fingerprint | 22 | 27C6-659A | no driver (switched off, noted) |
| Goodix fingerprint | 21 | 27C6-5395 | no driver (switched off, noted) |
| FPC Fingerprint Reader (Disum) | 21 | 10A5-9200 | no driver (switched off, noted) |
| Goodix fingerprint | 21 | 27C6-521D | no driver (switched off, noted) |
| Goodix fingerprint | 20 | 27C6-55A2 | no driver (switched off, noted) |
| Goodix fingerprint | 19 | 27C6-550A | no driver (switched off, noted) |
| Goodix fingerprint | 16 | 27C6-55A4 | no driver (switched off, noted) |
| ELAN WBF Fingerprint Sensor | 15 | 04F3-0C4F | no driver (switched off, noted) |
| Goodix MOC Fingerprint | 13 | 27C6-639C | no driver (switched off, noted) |
| ELAN WBF Fingerprint Sensor | 13 | 04F3-0C6E | no driver (switched off, noted) |
| Goodix Fingerprint USB Device | 13 | 27C6-5125 | no driver (switched off, noted) |
| ELAN WBF Fingerprint Sensor | 12 | 04F3-0C1A | no driver (switched off, noted) |
| FPC Fingerprint Reader | 11 | 10A5-D805 | no driver (switched off, noted) |
| Goodix MOC Fingerprint | 10 | 27C6-6594 | no driver (switched off, noted) |
| Synaptics WBDI - SGX | 9 | 06CB-009A | no driver (switched off, noted) |
| FPC Fingerprint Reader (Disum) | 9 | 10A5-A921 | no driver (switched off, noted) |
| FPC Fingerprint Reader | 8 | 10A5-9800 | no driver (switched off, noted) |
| Synaptics FP Sensors (WBF) (PID=003f) | 8 | 138A-003F | no driver (switched off, noted) |

## Input

2545 distinct devices. PCs by outcome: native or none needed 29964, kext 55.

