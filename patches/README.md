# 补丁系列

这些补丁由 `git format-patch` 从本 Fork 的实际提交导出，可用于审查、复现或回滚。全部基于官方 `v2.9`
（`03c79ef772f6142d59eb5203ce0efa98845bd0ba`）。

## upstream-fixes/（通用修复，适用于任何机器）

| 序号 | 提交 | 内容 |
|---|---|---|
| 0001 | `d197d82` | 擦盘前在打开的物理盘句柄上复核身份；diskpart 回退不再猜测旧磁盘号 |
| 0002 | `1e39b1c` | Windows 命令行参数按 `CommandLineToArgvW` 规则引用 |
| 0003 | `76a1edd` | 大于 256 GiB 的 USB 盘需要独立确认 |
| 0004 | `a28e174` | 完整安装器下载按目录大小封顶、超大 `.part` 重下、416/4xx 终止（#161） |
| 0005 | `1e4e4ba` | 本地 Recovery 镜像擦盘前完整校验；预检哈希首块 |
| 0006 | `9a753b4` | 依赖缓存子目录不可写时回退到 `-2/-3` |
| 0007 | `eb9d5e6` | 校验使用实际构建缓存的 OpenCore；打包检查绝对输出路径 |
| 0008 | `99aa068` | Windows UI：输出加锁、默认 Cancel、OS 盘未知时 fail-closed |
| 0009 | `97522ba` | 打包 SDK 断言不再包含 `initguid.h`（Windows SDK 10.0.22621 兼容） |
| 0010 | `5282485` | 隐私检查改用完整用户目录路径，避免用户名与厂商名相同 |
| 0011 | `4e00154` | 打包自检以 `RunAsInvoker` 运行（仅 `--verify-package`，真实使用仍要管理员） |
| 0012 | `7cd2cac` | 自检跟随当前下载器/VMD 文案/缓存回退/报告注释 |
| 0013 | `6d16d70` | 完整安装器首分区大小通过参数传递，不再修改模块全局 `PART_CAP` |
| 0014 | `9c30c6b` | 更新磁盘号测试对带 `cap` 的 diskpart 调用预期 |

应用顺序即编号顺序。每个补丁都带独立测试；应用后运行 `scripts/run-tests.cmd`。

## huawei/（MateBook X Pro 2023 专属）

| 序号 | 提交 | 内容 |
|---|---|---|
| 0001 | `15bba79` | `p1401/huawei.py`、Huawei 配方、AX211/itlwm 判定、UTBMap 状态、Intel Xe 通知 |
| 0002 | `f6882aa` | 从原始扫描读取 `Storage Drives`，使外置 TBU405Pro 通知生效 |
| 0003 | `318cd97` | 版本 2.9.1 与 CHANGELOG |

Huawei 补丁只在本机扫描匹配 `MRGFG-XX`/`MateBook X Pro` 且 CPU 含 `i7-1360P` 时生效，不改变通用规则。

## 应用/回滚

```bash
# 查看
git apply --stat patches/upstream-fixes/0001-*.patch

# 在 v2.9 之上按顺序应用（示例）
git checkout -b review/patches v2.9
git am patches/upstream-fixes/*.patch

# 回滚单个提交（在完整仓库中更简单）
git revert <commit>
```

补丁是审查/复现用途；日常开发请直接使用分支与提交历史（`main`、`develop`、`feature/huawei-1401`）。
