# Recovery 流程验证（真实 Apple 数据）

## 1. 结论

Recovery 路线在**下载与完整性**层面已完整验证：Apple 元数据、签名 chunklist、逐块 SHA-256、完整 960 MB 镜像下载、读回校验全部通过。**未验证**的是“把镜像写到 U 盘后真实启动 Recovery/安装 macOS”，因为本项目未获授权写真实磁盘。

## 2. 真实证据

### 2.1 Apple 元数据与签名 chunklist

`scripts/verify_recovery.py`（2026-11-11，本机）：

```json
{
 "ok": true,
 "darwin": 25,
 "product": "140-93589",
 "image": "BaseSystem.dmg",
 "bytes": 960530321,
 "chunks": 92,
 "chunklist_signature": "Apple EFI ROM RSA verified",
 "first_chunk_sha256_matches": true,
 "preflight_sampled_bytes": 10485760
}
```

- 目标：macOS 26 Tahoe（Darwin 25）。
- Apple 返回的产品号 `140-93589`，镜像 `BaseSystem.dmg`，**960,530,321 bytes**，**92 块**。
- `BaseSystem.chunklist` 用 Apple EFI ROM RSA 公钥验签通过；首块完整 **10,485,760 bytes**，其 SHA-256 与签名 chunklist 一致。
- 预检请求发生在任何擦盘之前；若失败，写盘器不会触碰 U 盘。

### 2.2 完整镜像下载 + 逐块校验 + 读回

实际执行 `apple.download()` 到项目目录 `out/recovery-test/com.apple.recovery.boot/`（未写任何真实 U 盘）：

```json
{
 "ok": true,
 "bytes": 960530321,
 "chunks": 92,
 "sha256": "edddd0d5869caaa12e29e6996a04f11590280580976a119dbd42c24fa62fe18e",
 "readback_changed": [],
 "seconds": 35.6
}
```

- 下载耗时约 36 秒；92 块全部通过 Apple 签名 chunklist 的 SHA-256。
- 写完后 `verify_written()` 以 Windows 无缓冲读回，**0 块不同**。
- 文件头为 UDIF DMG，尾部包含 `koly`  trailer；大小与 92 块之和一致。
- 日志：`reports/logs/recovery-full-download.log`；文件仍在 `out/recovery-test/`（可删除，非发布物）。

### 2.3 下载路径的失败恢复（源码 + 测试）

- 预检：`apple.preflight()` 在擦盘前取 chunklist + 完整首块并校验哈希（本项目修复 CORE-01）。
- 逐块：`apple.download()` 每块 SHA-256；坏块单独重取一次；仍坏则停止，并给出网络/杀毒软件/代理建议。
- 连接中断：进程内按字节 Range 续传，窗口模式、403 刷新 token、416 终止并说明“服务器给的不是 Apple 的镜像”。
- 末尾：`r.read(1)` 若有额外字节 → 拒绝“镜像大于签名 chunklist”。
- 本地镜像：`apple.verify_local()` 在擦盘前完整校验；`copy_local()` 逐块重试 + fsync；可选 `BaseSystem.product.json` 记录 `{product, darwin}`，与请求不符则拒绝。
- 测试：`tests/test_apple_preflight_hash.py`、`tests/test_apple_local_verify.py`、`tests/test_apple_resume.py`、`tests/test_apple_preflight_status.py` 等。

## 3. 资源完整性矩阵

| 检查 | 结果 |
|---|---|
| BaseSystem.dmg 存在 | 是（960,530,321 bytes） |
| BaseSystem.chunklist 存在 | 是（3,604 bytes） |
| chunklist 签名 | Apple EFI ROM RSA 通过 |
| 每块 SHA-256 | 92/92 通过 |
| 下载后读回 | 0 块不同 |
| 大小与 chunklist 总和 | 一致 |
| DMG 结构 | UDIF + `koly` trailer |
| 下载目录 | `out/recovery-test/com.apple.recovery.boot`（项目内，非 U 盘） |
| EFI 与 Recovery 对应 | 同一 Darwin 25 目标；EFI 由同一扫描生成 |
| `OS.dmg.root_hash` | **不是 Recovery 镜像的一部分**；见 `recovery/02` |

## 4. 未验证与边界

- **未写 U 盘**：`usbwriter write` 会擦除目标盘；本项目未获授权，未执行。
- **未启动 Recovery**：需要真实 U 盘 + 重启 + BIOS 设置。
- **未安装 macOS**：需要实机与授权。
- 在线安装的 macOS 26 内存盘限制（上游 #127）是 Apple 侧行为；完整安装器是替代路径（见 `recovery/03`）。
- `OS.dmg.root_hash` 的 `Err(0xE)` 是安装介质常见预检输出，不是本流程的失败原因。

## 5. 复现命令

```powershell
# 仅元数据/签名/首块（约 10 MB）
.\.venv\Scripts\python.exe scripts\verify_recovery.py --json-out reports\recovery\verification.json

# 完整镜像（约 960 MB，写项目目录，不写 U 盘）
.\.venv\Scripts\python.exe -m p1401.apple probe 25
# 或使用 apple.download()，见 reports/logs/recovery-full-download.log
```
