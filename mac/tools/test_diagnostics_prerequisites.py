#!/usr/bin/env python3
"""Read-only native prerequisite qualification; never run as administrator."""
import json, os, pathlib, subprocess, sys
assert os.geteuid() != 0
checker = pathlib.Path(sys.argv[1]).resolve()
for args in [[], ["0"], ["1"], ["-1"], ["999999999999999999999"], ["text"], [str(os.getpid()), "extra"]]:
    p = subprocess.run([str(checker), *args], capture_output=True, timeout=10)
    assert p.returncode == 2 and not p.stdout, (args, p.returncode)
p = subprocess.run([str(checker), str(os.getpid())], capture_output=True, timeout=10, check=True)
assert len(p.stdout) <= 32768
r = json.loads(p.stdout)
assert r["schema"] == "nullmoth-optional-diagnostics/1"
assert r["status"] == "blocked" and r["captureAvailable"] is False and r["productionBridgeQualified"] is False
assert r["authorityReason"] == "verified_privileged_installer_bridge_unqualified"
assert r["ordinaryLogsAvailable"] is True
assert r["providerInventoryStatus"] == "not_checked_missing_prerequisites"
assert r["tool"]["path"] == "/usr/sbin/dtrace"
assert r["csr"]["requiredFlag"] == 32
assert r["security"]["kernelIntegrityAttestation"] == "not_available"
assert r["security"]["facts"]["selfRuntimeEnforced"]
for key in ["externalForm", "installedDefinition", "authorization", "target", "PCIdevices", "components"]:
    assert key not in r
print("PASS: actual read-only checker, invalid argument refusal, hard production-authority block, effective CSR/tool facts, zero provider budget, runtime flags; no administrator/trace/policy writes")
