"""Compile the production Mach-O guard and test actual load-command boundaries."""
import pathlib
import struct
import subprocess
import tempfile
import unittest
import os as _os, pathlib as _pl
# the NVIDIA driver checkout these app/driver contract tests read (NULLMOTH_DRIVER, else the sibling driver/)
DRV = _pl.Path(_os.environ.get("NULLMOTH_DRIVER") or _pl.Path(__file__).resolve().parents[3] / "driver")

ROOT = pathlib.Path(__file__).resolve().parents[1]

def image(minimum=(15,5,0), command=0x32):
    packed=(minimum[0]<<16)|(minimum[1]<<8)|minimum[2]
    load=struct.pack('<6I',command,24,1,packed,packed,0) if command==0x32 else struct.pack('<4I',command,16,packed,packed)
    return struct.pack('<8I',0xfeedfacf,0x1000007,3,6,1,len(load),0,0)+load

class RuntimeMinimum(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(); cls.root=pathlib.Path(cls.temp.name)
        cls.tool=cls.root/'guard'
        subprocess.run(['xcrun','clang','-O2','-Wall','-Wextra','-Werror','-target','x86_64-apple-macos15.0',str(ROOT/'RuntimeCheck/main.c'),'-o',str(cls.tool)],check=True)
    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()
    def run_guard(self,host,data):
        path=self.root/'payload.dylib'; path.write_bytes(data)
        return subprocess.run([str(self.tool),host,str(path)],capture_output=True,text=True)
    def test_actual_minimum_is_enforced_without_metadata_changes(self):
        data=image()
        for host,expected in [('15.0',1),('15.4.9',1),('15.5',0),('15.8.1',0),('26.0',0)]:
            with self.subTest(host=host):
                checked=self.run_guard(host,data)
                self.assertEqual(checked.returncode,expected,checked.stdout+checked.stderr)
        self.assertEqual((self.root/'payload.dylib').read_bytes(),data)
    def test_legacy_minimum_and_patch_version_are_respected(self):
        self.assertEqual(self.run_guard('15.5.1',image((15,5,2),0x24)).returncode,1)
        self.assertEqual(self.run_guard('15.5.2',image((15,5,2),0x24)).returncode,0)
    def test_universal_x86_slice_is_checked(self):
        thin=image(); offset=8+20
        fat=struct.pack('>2I',0xcafebabe,1)+struct.pack('>5I',0x1000007,3,offset,len(thin),0)+thin
        self.assertEqual(self.run_guard('15.4',fat).returncode,1)
        self.assertEqual(self.run_guard('15.5',fat).returncode,0)
    def test_unknown_architecture_missing_declaration_and_truncation_refuse(self):
        wrong=bytearray(image());struct.pack_into('<I',wrong,4,0x100000c)
        absent=struct.pack('<8I',0xfeedfacf,0x1000007,3,6,0,0,0,0)
        huge=bytearray(image());struct.pack_into('<I',huge,36,0xfffffff8)
        for data in [wrong,absent,image()[:-1],huge]:
            self.assertEqual(self.run_guard('26.0',data).returncode,1)
    def test_invalid_host_version_is_not_a_pass(self):
        for text in ['','15..5','15.5.','15.5beta','26.0.0.1','-1.0','15.256','9999999999999999999999999']:
            self.assertEqual(self.run_guard(text,image()).returncode,1,text)
    def test_setup_guard_precedes_efi_mutation_and_standalone_backup(self):
        setup=(ROOT/'Resources/nullmoth-setup.sh').read_text()
        gate=setup.index('/bin/bash "$RUNTIME_PREFLIGHT" "$T/pkgroot"')
        self.assertLess(gate,setup.index('if [ -n "$CFG" ]; then C=$CFG'))
        installer=(DRV/'package/install.sh').read_text()
        self.assertLess(installer.index('/bin/bash "$RUNTIME_PREFLIGHT" "$HERE"'),installer.index('step "3. test kernel collection"'))

if __name__=='__main__':unittest.main()
