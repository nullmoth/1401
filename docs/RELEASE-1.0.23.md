# 1401 Windows 1.0.23

This maintenance refresh stages 1401 Mac 1.0.17 and driver helper package 1.0.11 on newly built installation sticks. Both downloads are pinned to their published SHA-256 values. The Windows app and manifest versions are 1.0.23.

The Mac helper creates unique recovery directories, refuses overlapping cooperating driver installers and retains bounded backup failure details. Existing recovery guards, unsafe parent directory ownership/permissions and symlinked parents stop installation for review. Changed guard identities are retained during cleanup; incomplete restoration retains the guard for recovery review. This guard covers the driver installer only, including its preflight and rollback. Earlier setup changes to OpenCore are outside it.

The Mac disk image contains the companion app and its instructions; the driver helper is a separate verified asset. Windows stages that helper alongside the companion for installation from the stick. Keep the startup OpenCore stick attached: automatic USB-to-internal EFI promotion remains disabled. Optional DTrace capture remains unavailable.

Windows hardware policies, USB behavior, portable Python baseline, runtime dependencies and OpenCore pins are unchanged. All 47 protected GPU/kernel/compiler/firmware/removal payload files and both runtime links remain unchanged in the refreshed helper. This update adds no per-machine graphics or macOS 26 qualification and does not establish the cause of an unlinked Tahoe backup report.

Distribution validation includes the actual Windows packaged application startup/version, native collectors, bounded-worker tests and offline planning fixtures before release. Mac source-bound signatures, package pins, archive contents and installer recovery checks are validated separately.
