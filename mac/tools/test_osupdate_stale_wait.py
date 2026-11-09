#!/usr/bin/env python3
"""A Mac prepared for Tahoe that never updates must not stay parked for good."""
from pathlib import Path
import os, subprocess, tempfile, time, unittest

root = Path(__file__).resolve().parents[1]
source = (root / 'Resources/nullmoth-setup.sh').read_text()
end = source.index('    if [ "$UPD" = finish ] && [ "${FROM:-}" = "$MAJ" ] && [ "$MAJ" = 15 ]; then echo')
block_start = source.rindex('    # A Mac that was prepared for Tahoe and never updated', 0, end)
block = source[block_start:end]

class StaleWait(unittest.TestCase):
    def run_block(self, age_days, installer):
        with tempfile.TemporaryDirectory() as d:
            pend = Path(d) / 'update-pending'
            pend.write_text('FROM=15\n')
            t = time.time() - age_days * 86400
            os.utime(pend, (t, t))
            fake = Path(d) / 'bin'; fake.mkdir()
            # the two installer locations are fixed paths on a real Mac; the test swaps the checks for flags
            script = block.replace('[ ! -d "/macOS Install Data" ]', '[ ! -e "$HAS_INSTALLER" ]') \
                          .replace('! ls -d /Applications/Install\\ macOS*.app >/dev/null 2>&1', 'true')
            script = 'note() { echo "NOTE $*"; }\nPEND="%s"\n' % pend + script + '\necho "UPD=$UPD"\n'
            inst = Path(d) / 'installer'
            if installer: inst.write_text('x')
            r = subprocess.run(['/bin/bash', '-c', script], capture_output=True, text=True,
                               env={'UPD': 'finish', 'FROM': '15', 'MAJ': '15', 'HAS_INSTALLER': str(inst), 'PATH': '/bin:/usr/bin'})
            return r.stdout

    def test_abandoned_update_turns_the_driver_back_on(self):
        self.assertIn('UPD=cancel', self.run_block(15, False))

    def test_a_recent_preparation_keeps_waiting(self):
        self.assertIn('UPD=finish', self.run_block(2, False))

    def test_a_staged_installer_keeps_waiting(self):
        self.assertIn('UPD=finish', self.run_block(30, True))

    def test_the_check_runs_before_the_waiting_exit(self):
        self.assertLess(block_start, end)
        self.assertIn('UPD=cancel', source[block_start:end])

if __name__ == '__main__':
    unittest.main()
