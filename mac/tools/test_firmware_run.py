#!/usr/bin/env python3
"""The Mac setup script hands NVIDIA's driver package (GPU firmware source) to the driver installer when it sits beside the
driver package, and never follows a link."""
import os, subprocess, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / 'Resources/nullmoth-setup.sh').read_text()
START = 'FWRUN_SRC="$(dirname "$PKG")/NVIDIA-Linux-x86_64-620.70.06.run"'
END = 'else unset NULLMOTH_FW_RUN; fi\n'


class FirmwareRun(unittest.TestCase):
    def run_block(self, setup):
        assert SRC.count(START) == 1 and SRC.count(END) == 1
        body = START + SRC.split(START, 1)[1].split(END, 1)[0] + END
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / 'stick/NullMoth').mkdir(parents=True)
            pkg = d / 'stick/NullMoth/nullmoth-nvidia-2.9.0.tar.gz'
            pkg.write_bytes(b'x')
            setup(d / 'stick/NullMoth')
            script = d / 's.sh'
            script.write_text('ok(){ :; }\nPKG=$1\nNULLMOTH_FW_RUN=stale\n' + body + 'echo "[${NULLMOTH_FW_RUN-unset}]"\n')
            r = subprocess.run(['/bin/bash', str(script), str(pkg)], capture_output=True, text=True)
            return r.stdout.strip(), str(d)

    def test_a_file_beside_the_package_is_passed_on(self):
        out, d = self.run_block(lambda n: (n / 'NVIDIA-Linux-x86_64-620.70.06.run').write_bytes(b'r'))
        self.assertTrue(out.endswith('NVIDIA-Linux-x86_64-620.70.06.run]') and 'unset' not in out and 'stale' not in out)

    def test_without_the_file_the_variable_is_cleared(self):
        out, _ = self.run_block(lambda n: None)
        self.assertEqual(out, '[unset]')

    def test_a_link_is_not_followed(self):
        out, _ = self.run_block(lambda n: os.symlink('/etc/hosts', n / 'NVIDIA-Linux-x86_64-620.70.06.run'))
        self.assertEqual(out, '[unset]')

    def test_the_pin_matches_the_driver_installer(self):
        drv = os.environ.get('NULLMOTH_DRIVER')
        f = Path(drv or '') / 'package/fw_fetch.sh'
        if not f.is_file():
            self.skipTest('NULLMOTH_DRIVER not set')
        self.assertIn('NVIDIA-Linux-x86_64-$VER.run', f.read_text())
        self.assertIn('NVIDIA-Linux-x86_64-620.70.06.run', SRC)


if __name__ == '__main__':
    unittest.main()
