"""Setup switches IntelBTPatcher.kext off only when this Mac's own saved panic shows it crashing bluetoothd.

Uploads 10-22..10-28: 24 "IOGMD: not wired for the IODMACommand" panics from 7 Tahoe laptops, IntelBTPatcher in every
backtrace (upstream OpenIntelWireless/IntelBluetoothFirmware #486). A panic from another kext, or the kext only in the
loaded-kext list, must leave the config alone.
"""
import pathlib
import plistlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
source = (ROOT / "Resources/nullmoth-setup.sh").read_text()
start = source.index("# IntelBTPatcher can panic bluetoothd")
end = source.index("# Tahoe preparation:", start)
BLOCK = source[start:end]
FIXED = "PANICDIR=/Library/Logs/DiagnosticReports"
assert BLOCK.count(FIXED) == 1, "setup must name the panic folder itself"
BLOCK = BLOCK.replace(FIXED, 'PANICDIR="$2"')

HARNESS = r'''
set -u
C="$1"; EDITS=()
get() { plutil -extract "$1" raw -o - "$C" 2>/dev/null; }
kpos() { local i=0 p; while p=$(get Kernel.Add.$i.BundlePath); do [ "$p" = "$1" ] && { echo $i; return; }; i=$((i+1)); done; }
''' + BLOCK + r'''
printf 'EDIT %s\n' "${EDITS[@]+"${EDITS[@]}"}"
'''

BT = ('panic(cpu 2 caller 0xffffff80054dea7e): IOGMD: not wired for the IODMACommand @IOMemoryDescriptor.cpp:3537\\n'
      'Backtrace (CPU 2)\\n      Kernel Extensions in backtrace:\\n'
      '         com.apple.iokit.IOUSBHostFamily(1.2)[x]@0x1->0x2\\n         com.zxystd.IntelBTPatcher(2.4)[x]@0x3->0x4\\n')
LISTED_ONLY = ('panic(cpu 0 caller 0x1): IOGMD: not wired for the IODMACommand\\nKernel Extensions in backtrace:\\n'
               '         com.apple.iokit.IOUSBHostFamily(1.2)\\nloaded kexts:\\ncom.zxystd.!IBTPatcher\\t2.4.0\\n')


def run(panic_text, enabled=True):
    with tempfile.TemporaryDirectory() as d:
        cfg = pathlib.Path(d, "config.plist")
        kexts = [{"BundlePath": "Lilu.kext", "Enabled": True},
                 {"BundlePath": "IntelBTPatcher.kext", "Enabled": enabled}]
        cfg.write_bytes(plistlib.dumps({"Kernel": {"Add": kexts}}))
        pd = pathlib.Path(d, "reports"); pd.mkdir()
        if panic_text is not None:
            pd.joinpath("Kernel-2026-10-28-153524.panic").write_text('{"bug_type":"210"}\n{"macOSPanicString":"%s"}' % panic_text)
        r = subprocess.run(["/bin/bash", "-c", HARNESS, "h", str(cfg), str(pd)], capture_output=True, text=True,
                           env={"PATH": "/usr/bin:/bin"})
        return r.returncode, r.stdout


class BTPatcherPanic(unittest.TestCase):
    def test_its_own_panic_turns_it_off(self):
        rc, out = run(BT)
        self.assertEqual(rc, 0, out)
        self.assertIn("EDIT Kernel.Add.1.Enabled|-bool|false", out)
        self.assertIn("CHANGE Kernel -> Add: turn IntelBTPatcher.kext off", out)

    def test_no_panic_changes_nothing(self):
        self.assertNotIn("Kernel.Add.1", run(None)[1])

    def test_a_panic_where_it_is_only_loaded_changes_nothing(self):
        self.assertNotIn("Kernel.Add.1", run(LISTED_ONLY)[1])

    def test_already_off_is_left_alone(self):
        self.assertNotIn("Kernel.Add.1", run(BT, enabled=False)[1])


if __name__ == "__main__":
    unittest.main()
