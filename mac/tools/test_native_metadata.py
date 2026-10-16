"""Synthetic production metadata/checkpoint regressions; no hardware queries or installation."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "Sources"


@unittest.skipUnless(sys.platform == "darwin" and shutil.which("xcrun"), "Requires the macOS Swift SDK")
class NativeMetadataTests(unittest.TestCase):
    def compile_fixture(self, sources, executable, frameworks=()):
        command = ["xcrun", "swiftc", "-O", "-sanitize=address"]
        for framework in frameworks:
            command += ["-framework", framework]
        command += [str(source) for source in sources] + ["-o", str(executable)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stderr)

    def run_fixture(self, executable, arguments=()):
        result = subprocess.run([str(executable), *map(str, arguments)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("ERROR: AddressSanitizer", result.stderr)
        return result.stdout

    def test_native_audio_display_metadata_without_native_calls(self):
        with tempfile.TemporaryDirectory(prefix="nullmoth-metadata-test-") as directory:
            output = Path(directory) / "metadata-test"
            self.compile_fixture([SOURCES / "NativePeripheralFacts.swift", ROOT / "tools/native_metadata_tests/main.swift"], output,
                                 frameworks=["CoreAudio", "CoreGraphics"])
            self.assertIn("78", self.run_fixture(output))

    def test_checkpoint_protocol_and_owned_child_cleanup(self):
        names = ["normal", "legacy", "timeout", "signal", "failure", "malformed", "truncated", "truncated-success",
                 "overflow", "small-cap", "changed-baseline", "missing-baseline-field", "wrong-phase", "overnodes-final",
                 "missing-final", "emitter-cap", "third-record", "empty-extra", "invalid-baseline", "unavailable-overnodes",
                 "final-then-failure", "final-then-timeout", "final-then-signal"]
        with tempfile.TemporaryDirectory(prefix="nullmoth-checkpoint-test-") as directory:
            folder = Path(directory)
            folder.chmod(0o700)
            fixture = folder / "fixture"
            self.compile_fixture([SOURCES / "HardwareMapWorker.swift", ROOT / "tools/hardware_checkpoint_tests/fixture/main.swift"], fixture)
            for name in names:
                shutil.copy2(fixture, folder / name)
            test = folder / "checkpoint-test"
            self.compile_fixture([SOURCES / "HardwareMapWorker.swift", ROOT / "tools/hardware_checkpoint_tests/main.swift"], test)
            self.assertIn("159 checkpoint assertions", self.run_fixture(test, [folder]))

    def test_registry_refusal_keeps_cpu_and_unavailable_qualification(self):
        with tempfile.TemporaryDirectory(prefix="nullmoth-registry-test-") as directory:
            test = Path(directory) / "registry-test"
            self.compile_fixture([SOURCES / "profile.swift", SOURCES / "HardwareMap.swift", SOURCES / "HardwareMapWorker.swift",
                                  ROOT / "tools/registry_failure_tests/main.swift"], test, frameworks=["IOKit"])
            self.assertIn("14 pure registry-refusal", self.run_fixture(test))


if __name__ == "__main__":
    unittest.main()
