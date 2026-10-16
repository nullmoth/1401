"""Execute production automatic EFI selection without system calls or disk writes."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'Resources/nullmoth-setup.sh').read_text()
a=source.index('  if [ "$EFI" = auto ]; then')
b=source.index('  mount_efi "$EFI"',a)
selection=source[a:b]
MOCK=r'''
EFI=auto; MOUNT_POINT=''
stop() { echo "STOP $*"; exit 17; }
ok() { echo "OK $*"; }
mount_efi() { MOUNT_POINT=$1; }
ocrel_in() { echo EFI/OC; }
booted_part() { [ -n "$FIXTURE_BOOT_PART" ] && echo "$FIXTURE_BOOT_PART"; }
boot_esp() { echo "$FIXTURE_SYSTEM_PART"; }
diskutil() { for d in $FIXTURE_CANDIDATES; do echo "1: EFI fixture 200MB $d"; done; }
'''
class EfiOwnership(unittest.TestCase):
    def run_selection(self,boot='',system='',candidates='disk1s1'):
        with tempfile.TemporaryDirectory() as directory:
            script=Path(directory)/'selection.sh';script.write_text(MOCK+selection+'\necho "SELECTED $EFI"\n')
            env=dict(os.environ,FIXTURE_BOOT_PART=boot,FIXTURE_SYSTEM_PART=system,FIXTURE_CANDIDATES=candidates)
            return subprocess.run(['/bin/bash',str(script)],env=env,capture_output=True,text=True)
    def test_same_model_single_candidate_does_not_establish_boot_ownership(self):
        result=self.run_selection(system='disk1s1')
        self.assertEqual(result.returncode,17,result.stdout+result.stderr)
        self.assertIn('NOTE candidate disk1s1',result.stdout)
        self.assertNotIn('SELECTED',result.stdout)
    def test_system_disk_preference_does_not_override_missing_boot_proof(self):
        result=self.run_selection(system='disk2s1',candidates='disk1s1 disk2s1')
        self.assertEqual(result.returncode,17,result.stdout+result.stderr)
        self.assertIn('NOTE candidate disk1s1',result.stdout)
        self.assertIn('NOTE candidate disk2s1',result.stdout)
        self.assertNotIn('SELECTED',result.stdout)
    def test_verified_boot_partition_wins_over_other_candidates(self):
        result=self.run_selection(boot='disk1s1',system='disk2s1',candidates='disk1s1 disk2s1')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('SELECTED disk1s1',result.stdout)
        self.assertNotIn('NOTE candidate',result.stdout)

if __name__=='__main__':unittest.main()
