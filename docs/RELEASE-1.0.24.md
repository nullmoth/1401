# 1401 Windows 1.0.24

This update saves a unique local diagnostic record before every engine scan, build or USB-writing attempt, and a final record after completion or failure. Reports include the operation, exit code, observed app/engine/tool hashes when available, declared companion pins and bounded redacted output. Engine launch failures and malformed results now offer a saved report instead of returning without one. Reports remain available after restart and unsuccessful uploads. Failure to save is shown explicitly; an attempt does not start when its initial report cannot be saved.

Dependency ZIP downloads are staged in separate temporary files and checked for a readable central directory before replacing an existing archive. Invalid ZIP responses retry up to three times and retain the previous archive. Diagnostics record failed response size and hash without response body content. Existing checksum requirements remain enforced. This check does not qualify ZIP extraction paths or establish the cause of an unmatched report.

The package continues to include Mac 1.0.17 and helper 1.0.11. Hardware routing protections, firmware settings and graphics payloads are unchanged. No new MUX, GPU, application, DRM or macOS 26 support is claimed. An ACPI compiler crash requires its exact input and tool evidence before a machine-specific fix can be qualified.

Validation requires the compiled Windows local-report lifecycle fixture, full application build, packaged startup/version and native collector checks, alongside the Python download and early-build regressions. Process termination or unavailable storage can leave only the attempt-start record; reports are never described as saved if saving failed.
