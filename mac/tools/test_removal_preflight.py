#!/usr/bin/env python3
"""Exercise the removal transaction against temporary configs and command mocks."""
import hashlib, os, plistlib, subprocess, sys, tempfile, unittest
from pathlib import Path
import os as _os, pathlib as _pl
# the NVIDIA driver checkout these app/driver contract tests read (NULLMOTH_DRIVER, else the sibling driver/)
DRV = _pl.Path(_os.environ.get("NULLMOTH_DRIVER") or _pl.Path(__file__).resolve().parents[3] / "driver")

ROOT = Path(__file__).resolve().parents[1]
BOOT = '7C436110-AB2A-4BBB-A880-FE41995C9F82'
MOCK = r'''
import os,sys
from pathlib import Path
n=Path(sys.argv[0]).name;a=sys.argv[1:];r=Path(os.environ['FIXTURE_ROOT'])
if n=='id':print(0)
elif n=='diskutil':
 with (r/'disk-calls').open('a') as f:f.write(' '.join(a)+'\n')
 if os.environ.get('MISSING_ESP'):sys.exit(8)
 if a[0]=='info':
  if not os.environ.get('MOUNT_ON_REQUEST') or (r/'mounted').exists():print('Mount Point: '+str(r/'esp'))
 elif a[0]=='mount':(r/'mounted').write_text('mounted')
 elif a[0]=='unmount':(r/'mounted').unlink()
elif n=='plutil':
 if a[0] in ['-replace','-remove'] and a[1]==os.environ.get('FAIL_EDIT'):sys.exit(9)
 os.execv('/usr/bin/plutil',['plutil']+a)
elif n=='mv':
 if os.environ.get('FAIL_PUBLISH') and a[-1]==str(r/'esp/EFI/OC/config.plist'):sys.exit(9)
 os.execv('/bin/mv',['mv']+a)
else:sys.exit(99)
'''

class RemovalPreflight(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.r=Path(self.temp.name)
        self.bin=self.r/'bin';self.bin.mkdir()
        for n in ['id','diskutil','plutil','mv']:
            p=self.bin/n;p.write_text('#!'+sys.executable+'\n'+MOCK);p.chmod(0o755)
        self.env=dict(os.environ,PATH=str(self.bin)+':/usr/bin:/bin:/usr/sbin:/sbin',FIXTURE_ROOT=str(self.r))
        self.st=self.r/'Library/NullMoth';self.st.mkdir(parents=True)
        self.oc=self.r/'esp/EFI/OC';self.oc.mkdir(parents=True)
        self.cfg=self.oc/'config.plist';self.back=self.oc/'config.plist.backup'
        self.config={'NVRAM':{'Add':{BOOT:{'boot-args':'-v nvfb=1 nvaccel=1 -nvoff custom=1','csr-active-config':bytes(4)}}},
            'Misc':{'Security':{'SecureBootModel':'Disabled'},'Tools':[{'Path':'NullMothSafe.efi'}]},
            'UEFI':{'Quirks':{'ResizeGpuBars':13}},'Booter':{'Quirks':{'ResizeAppleGpuBars':-1}},
            'Kernel':{'Block':[{'Identifier':'com.apple.iokit.IONDRVSupport','Enabled':True}]}}
        self.cfg.write_bytes(plistlib.dumps(self.config));self.back.write_bytes(self.cfg.read_bytes())
        self.state=self.st/'state'
        self.state.write_text("EFI_UUID='original-esp'\nOCREL='EFI/OC'\nCONFIG_BACKUP_REL='EFI/OC/config.plist.backup'\nCONFIG_SHA_AFTER='changed'\nADDED_ARGS=''\nREMOVED_ARGS=''\nOLD_CSR=0\nNEW_CSR=2563\nOLD_SBM='Default'\n")
        self.recover=self.r/'Library/LaunchDaemons/com.nullmoth.recover.plist';self.recover.parent.mkdir(parents=True);self.recover.write_text('keep')
        self.tool=self.oc/'Tools/NullMothSafe.efi';self.tool.parent.mkdir();self.tool.write_bytes(b'keep')
        source=(ROOT/'Resources/nullmoth-setup.sh').read_text().replace('PATH=/usr/bin:/bin:/usr/sbin:/sbin\n','')
        source=source.replace('/Library/',str(self.r)+'/Library/')
        self.script=self.r/'nullmoth-setup.sh';self.script.write_text(source)
        un=self.r/'nullmoth-uninstall.sh';un.write_text('#!/bin/bash\necho called >> "$FIXTURE_ROOT/uninstall-calls"\n[ "${FAIL_UNINSTALL:-0}" = 1 ] && exit 8\nexit 0\n');un.chmod(0o755)
    def tearDown(self):self.temp.cleanup()
    def run_remove(self,*extra,**faults):
        return subprocess.run(['/bin/bash',str(self.script),'--remove',*extra],env=dict(self.env,**faults),capture_output=True,text=True)
    def assert_preflight_stop(self,result):
        self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertFalse((self.r/'uninstall-calls').exists())
        self.assertEqual(plistlib.loads(self.cfg.read_bytes()),self.config)
        self.assertTrue(self.state.exists());self.assertTrue(self.recover.exists());self.assertTrue(self.tool.exists())
    def test_missing_recorded_partition_stops_before_removal(self):self.assert_preflight_stop(self.run_remove(MISSING_ESP='1'))
    def test_missing_backup_removes_only_driver_settings_from_proven_partition(self):
        self.back.unlink();r=self.run_remove();self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        c=plistlib.loads(self.cfg.read_bytes())
        self.assertEqual(c['NVRAM']['Add'][BOOT]['boot-args'],'-v custom=1')
        self.assertEqual(c['Misc']['Tools'],[])
        self.assertFalse(self.state.exists())
    def test_failed_config_edit_stops_before_removal(self):self.assert_preflight_stop(self.run_remove(FAIL_EDIT='UEFI.Quirks.ResizeGpuBars'))
    def test_failed_uninstaller_preserves_config_and_recovery(self):
        r=self.run_remove(FAIL_UNINSTALL='1');self.assertNotEqual(r.returncode,0)
        self.assertEqual(plistlib.loads(self.cfg.read_bytes()),self.config);self.assertTrue(self.recover.exists());self.assertTrue(self.state.exists())
    def test_failed_publication_preserves_recovery(self):
        r=self.run_remove(FAIL_PUBLISH='1');self.assertNotEqual(r.returncode,0)
        self.assertTrue(self.recover.exists());self.assertTrue(self.tool.exists());self.assertTrue(self.state.exists())
    def test_upgrade_backup_cannot_restore_old_driver_settings(self):
        digest=hashlib.sha256(self.cfg.read_bytes()).hexdigest()
        self.state.write_text(self.state.read_text().replace("CONFIG_SHA_AFTER='changed'", "CONFIG_SHA_AFTER='"+digest+"'"))
        r=self.run_remove();self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        c=plistlib.loads(self.cfg.read_bytes())
        self.assertEqual(c['NVRAM']['Add'][BOOT]['boot-args'],'-v custom=1')
        self.assertEqual(c['Misc']['Tools'],[])
        self.assertEqual(c['UEFI']['Quirks']['ResizeGpuBars'],-1)
        self.assertFalse(c['Kernel']['Block'][0]['Enabled'])
    def test_removal_clears_only_owned_update_parking_entries(self):
        self.config['Kernel']['Block'] += [
            {'Identifier':'com.nullmoth.NVAccel','Enabled':True,'Comment':'park the OS-specific accelerator during a macOS update'},
            {'Identifier':'org.example.Other','Enabled':True,'Comment':'keep'}]
        self.cfg.write_bytes(plistlib.dumps(self.config))
        r=self.run_remove();self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        blocks=plistlib.loads(self.cfg.read_bytes())['Kernel']['Block']
        self.assertEqual(len(blocks),2);self.assertEqual(blocks[1]['Identifier'],'org.example.Other')
    def test_newly_mounted_partition_is_unmounted_after_removal(self):
        r=self.run_remove(MOUNT_ON_REQUEST='1');self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertFalse((self.r/'mounted').exists())
        calls=(self.r/'disk-calls').read_text().splitlines()
        self.assertIn('mount original-esp',calls);self.assertIn('unmount original-esp',calls)
    def test_preexisting_mount_is_left_mounted(self):
        r=self.run_remove();self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertFalse(any(c.startswith('unmount ') for c in (self.r/'disk-calls').read_text().splitlines()))
    def test_new_mount_is_cleaned_up_on_preflight_failure(self):
        self.assert_preflight_stop(self.run_remove(MOUNT_ON_REQUEST='1',FAIL_EDIT='UEFI.Quirks.ResizeGpuBars'))
        self.assertFalse((self.r/'mounted').exists())
    def test_a_driver_with_no_install_record_is_still_removed(self):
        self.state.unlink()
        r=self.run_remove('--efi','replacement-esp');self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        c=plistlib.loads(self.cfg.read_bytes())
        self.assertEqual(c['NVRAM']['Add'][BOOT]['boot-args'],'-v custom=1')
        self.assertEqual(c['Misc']['Tools'],[])
        self.assertTrue((self.r/'uninstall-calls').exists())
    def test_selected_replacement_partition_can_be_used(self):
        r=self.run_remove('--efi','replacement-esp');self.assertEqual(r.returncode,0,r.stdout+r.stderr)
    def test_success_preserves_unrelated_args_and_removes_driver_args(self):
        r=self.run_remove();self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        c=plistlib.loads(self.cfg.read_bytes())
        self.assertEqual(c['NVRAM']['Add'][BOOT]['boot-args'],'-v custom=1')
        self.assertFalse(self.recover.exists());self.assertFalse(self.tool.exists());self.assertFalse(self.state.exists())
        self.assertEqual(c['UEFI']['Quirks']['ResizeGpuBars'],-1)

    def test_preexisting_amfi_args_survive_original_backup_restore(self):
        original_args='-v amfi=0x80 amfi_get_out_of_my_way=0x1 custom=1'
        original=plistlib.loads(self.back.read_bytes());original['NVRAM']['Add'][BOOT]['boot-args']=original_args
        self.back.write_bytes(plistlib.dumps(original))
        self.config['NVRAM']['Add'][BOOT]['boot-args']=original_args+' nvfb=1 nvaccel=1 nvfbheads=4 -nvkmsnosmooth'
        self.cfg.write_bytes(plistlib.dumps(self.config))
        digest=hashlib.sha256(self.cfg.read_bytes()).hexdigest()
        self.state.write_text(self.state.read_text().replace("CONFIG_SHA_AFTER='changed'", "CONFIG_SHA_AFTER='"+digest+"'").replace("ADDED_ARGS=''", "ADDED_ARGS='nvfb=1 nvaccel=1 nvfbheads=4 -nvkmsnosmooth'"))
        result=self.run_remove();self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(plistlib.loads(self.cfg.read_bytes())['NVRAM']['Add'][BOOT]['boot-args'],original_args)

    def test_preexisting_amfi_args_survive_unrelated_config_edits(self):
        self.config['NVRAM']['Add'][BOOT]['boot-args']='-v amfi=0x80 amfi_get_out_of_my_way=0x1 custom=1 nvfb=1 nvaccel=1 nvfbheads=4 -nvkmsnosmooth -nvoff'
        self.cfg.write_bytes(plistlib.dumps(self.config))
        self.state.write_text(self.state.read_text().replace("ADDED_ARGS=''", "ADDED_ARGS='nvfb=1 nvaccel=1 nvfbheads=4 -nvkmsnosmooth'"))
        result=self.run_remove();self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(plistlib.loads(self.cfg.read_bytes())['NVRAM']['Add'][BOOT]['boot-args'],'-v amfi=0x80 amfi_get_out_of_my_way=0x1 custom=1')

    def test_recorded_owned_amfi_args_are_removed(self):
        self.config['NVRAM']['Add'][BOOT]['boot-args']='-v amfi=0x80 amfi_get_out_of_my_way=0x1 custom=1 nvfb=1 nvaccel=1'
        self.cfg.write_bytes(plistlib.dumps(self.config))
        self.state.write_text(self.state.read_text().replace("ADDED_ARGS=''", "ADDED_ARGS='nvfb=1 nvaccel=1 amfi=0x80 amfi_get_out_of_my_way=0x1'"))
        result=self.run_remove();self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(plistlib.loads(self.cfg.read_bytes())['NVRAM']['Add'][BOOT]['boot-args'],'-v custom=1')

    def test_removed_driver_parking_arg_is_not_reintroduced(self):
        self.state.write_text(self.state.read_text().replace("REMOVED_ARGS=''", "REMOVED_ARGS='-nvoff custom=1'"))
        result=self.run_remove();self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(plistlib.loads(self.cfg.read_bytes())['NVRAM']['Add'][BOOT]['boot-args'],'-v custom=1')

    def inherited_ownership(self,record=None,uuid='fixture-partition',path='/fixture/EFI/OC/config.plist',ocrel='EFI/OC',digest='fixture-hash',args='-v amfi=0x80 amfi_get_out_of_my_way=0x1'):
        text=(ROOT/'Resources/nullmoth-setup.sh').read_text()
        start=text.index('owned_amfi_from_prior_record() (');end=text.index('\n)\n',start)+3
        prior=self.r/'prior-state'
        prior.write_text(record if record is not None else "EFI_UUID='fixture-partition'\nCONFIG_PATH='/fixture/EFI/OC/config.plist'\nOCREL='EFI/OC'\nCONFIG_SHA_AFTER='fixture-hash'\nADDED_ARGS='nvfb=1 amfi=0x80 amfi_get_out_of_my_way=0x1 -v'\n")
        command=text[start:end]+'\nowned_amfi_from_prior_record "$@"'
        result=subprocess.run(['/bin/bash','-c',command,'fixture',str(prior),uuid,path,ocrel,digest,args],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        return result.stdout.splitlines()

    def test_matching_prior_record_preserves_explicit_amfi_ownership(self):
        self.assertEqual(self.inherited_ownership(),['amfi=0x80','amfi_get_out_of_my_way=0x1'])

    def test_prior_ownership_requires_exact_partition_config_and_hash(self):
        for overrides in [{'uuid':'different-partition'},{'path':'/fixture/EFI/BOOT/config.plist'},{'ocrel':'EFI/BOOT'},{'digest':'changed-hash'},{'uuid':''}]:
            with self.subTest(overrides=overrides):self.assertEqual(self.inherited_ownership(**overrides),[])

    def test_legacy_or_invalid_prior_record_cannot_claim_ownership(self):
        for record in ["ADDED_ARGS='amfi=0x80'\n", 'return 9\n']:
            with self.subTest(record=record):self.assertEqual(self.inherited_ownership(record=record),[])

    def test_only_recorded_amfi_tokens_still_present_are_inherited(self):
        self.assertEqual(self.inherited_ownership(args='-v amfi=0x80'),['amfi=0x80'])
        record="EFI_UUID='fixture-partition'\nCONFIG_PATH='/fixture/EFI/OC/config.plist'\nOCREL='EFI/OC'\nCONFIG_SHA_AFTER='fixture-hash'\nADDED_ARGS='nvfb=1'\n"
        self.assertEqual(self.inherited_ownership(record=record),[])

if __name__=='__main__':unittest.main(verbosity=2)
