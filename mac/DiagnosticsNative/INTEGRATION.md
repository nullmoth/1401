# Optional diagnostics integration boundary

This release exposes a read-only prerequisite check and an explicit saved-receipt import. It does not install a helper, register a launch daemon or Authorization right, start or enumerate DTrace probes, or change operating-system security settings. The native checker refuses execution as root and invokes the reviewed prerequisite module with provider budget zero. Both the native response and app integration keep production capture unavailable.

## Installation authority audit

The current main app is ad-hoc signed by its existing build procedure. Its normal installation and log-collection paths invoke a mutable bundled shell resource through an administrator AppleScript prompt. The driver archive checksum is compared with a value supplied by that app. Those mechanisms do not establish an independently authenticated privileged diagnostics installation entry. Ad-hoc signatures, resource self-hashes and an app-supplied receipt cannot establish release provenance.

Consequently this integration does not invoke the proposed native diagnostics bootstrap or launch a separately downloaded diagnostics client. Matching root-owned component/right receipts are displayed only as read-only evidence; they do not override the hard production-bridge block. The reviewed native bootstrap, final signed client/helper, compiled release pins and installer transaction remain separate private review artifacts. A future integration must put those complete final bytes and generated bootstrap pins into an independently verified privileged installer, qualify its actual elevation/registration/right/rollback behavior, and qualify capture under a compatible policy before changing this release gate. No personal signing certificate or invented publisher identity is used.

## User actions and privacy

The Optional diagnostics button performs only a bounded read-only check. It reports actual Apple DTrace tool signature, CSR permission, observed authority-policy blockers and missing installation qualification. Provider availability is deferred to a future reviewed explicit administrator session. Ordinary hardware maps, kernel logs and saved panic/crash reports retain their existing collection path.

Import saved receipt opens a local file picker. It accepts a supported session envelope only with that session's explicit upload permission. A selected file must be an owned regular single-link file with mode 0600, a non-writable owned parent, no symlink path and at most 64 KiB. Every recognized nested field is type/size checked; unknown fields, arbitrary text, external forms and right definitions are refused. The receipt is stored separately in an owned mode-0700 directory as a mode-0600 file.

The separate Send logs action and confirmation are still required. At that point the receipt is read and validated again; only an allowlisted count/configuration projection is appended to the ordinary upload batch. The projection excludes session/boot UUIDs, PID/start time, executable file identity, device registry identity, model name and raw text. It retains numeric PCI/configuration facts, fixed component identifiers/hashes and bounded counts, and marks imported receipts as not independently authenticated. Import alone sends nothing. A refused receipt does not prevent other logs from being collected.

## Verification

Run `tools/test_optional_diagnostics.sh <built-private-app>` for assert-enabled Swift consent/schema/privacy/private-file tests, bounded checker worker failure/timeout cleanup tests, actual web UI event/text-safety tests, and actual read-only native checker checks. Builds preserve the main app's existing signing policy; the read-only child is hardened with library validation. No test writes Authorization DB, registers a privileged service or starts tracing. Actual root installer authority, positive administrator capture transport, live UI dialogs, compatible-policy capture/cleanup and OS 15/26 capture parity remain unqualified.
