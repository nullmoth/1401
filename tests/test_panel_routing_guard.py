"""Output-target and pre-mutation safety regressions; synthetic same-run observations only."""
import copy,ctypes,io,json,tempfile,unittest
from contextlib import nullcontext,redirect_stdout
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
from p1401 import devicemap as dm,engine,hwcapture,nullmoth,panel_guard,scan_evidence
NVIDIA={'vendor_id':0x10de,'device_id':0x25a2,'subsys_id':0x16731043,'luid':(0,11)}
INTEL={'vendor_id':0x8086,'device_id':0x4626,'subsys_id':0x16731043,'luid':(0,22)}
PNP=[{'node':'n0','hardware_ids':['PCI\\VEN_10DE&DEV_25A2&SUBSYS_16731043']},{'node':'n1','hardware_ids':['PCI\\VEN_8086&DEV_4626&SUBSYS_16731043']}]
PATH={'source_luid':(0,11),'target_luid':(0,22),'target_index':0,'output_technology':11,'target_available':True,'active':True}
REPORT={'Motherboard':{'Name':'Fixture board','Platform':'Laptop'},'CPU':{'Manufacturer':'Intel','Processor Name':'Fixture CPU'},'GPU':{
 'Discrete adapter':{'Manufacturer':'NVIDIA','Device Type':'Discrete GPU','Device ID':'10DE-25A2','Subsystem ID':'16731043','PCI Path':'PciRoot(0x0)/Pci(0x1,0x0)/Pci(0x0,0x0)','Compatibility':nullmoth.SEQUOIA},
 'Integrated adapter':{'Manufacturer':'Intel','Device Type':'Integrated GPU','Device ID':'8086-4626','Subsystem ID':'16731043','PCI Path':'PciRoot(0x0)/Pci(0x2,0x0)','Compatibility':(None,None)}}}
DISABLED={'Integrated GPU: Integrated adapter':REPORT['GPU']['Integrated adapter']}
def evidence(graph=None):
 value=hwcapture.empty_native('synthetic fixture');value['device_map']['graphics']=dm.measured(graph if graph is not None else dm.build_graphics_map([NVIDIA,INTEL],[PATH],PNP),'same-capture facts');value['scan_binding']={'status':'same_scan_run','scan_status':'complete'};return value
class Routing(unittest.TestCase):
 def test_distinct_render_and_output_adapters(self):
  graph=dm.build_graphics_map([NVIDIA,INTEL],[PATH],PNP);self.assertFalse(graph[0]['displays']);panel=graph[1]['displays'][0];self.assertEqual((panel['source_adapter'],panel['output_adapter']),('a0','a1'))
 def test_source_only_observation_is_not_target_route(self):
  p=dict(PATH);p.pop('target_luid');self.assertTrue(all(not a['displays'] for a in dm.build_graphics_map([NVIDIA,INTEL],[p],PNP)))
 def test_duplicate_target_luid_is_not_overwritten(self):
  self.assertTrue(all(not a['displays'] for a in dm.build_graphics_map([NVIDIA,INTEL,dict(INTEL)],[PATH],PNP)))
 def test_native_path_preserves_both_luids_ids_active(self):
  def sizes(flags,np,nm):ctypes.cast(np,ctypes.POINTER(ctypes.c_uint32))[0]=1;ctypes.cast(nm,ctypes.POINTER(ctypes.c_uint32))[0]=0;return 0
  def query(flags,np,paths,nm,modes,topology):
   p=paths[0];p.sourceInfo.adapterId.LowPart=11;p.sourceInfo.id=3;p.targetInfo.adapterId.LowPart=22;p.targetInfo.id=9;p.targetInfo.outputTechnology=11;p.targetInfo.targetAvailable=1;p.flags=1;return 0
  paths,errors=dm.display_paths(NS(need=lambda *a:None,f={'GetDisplayConfigBufferSizes':sizes,'QueryDisplayConfig':query}));self.assertEqual(errors,[]);self.assertEqual((paths[0]['source_luid'],paths[0]['target_luid']),((0,11),(0,22)));self.assertEqual((paths[0]['source_id'],paths[0]['target_id']),(3,9));self.assertTrue(paths[0]['active'])
class Safety(unittest.TestCase):
 def test_malformed_nested_evidence_cannot_become_a_panel_decision(self):
  for capture in (None,[],{'scan_binding':[]},{'scan_binding':{'status':'same_scan_run','scan_status':'complete'},'device_map':[]}):
   panel_guard.refuse_active_panel_disable(DISABLED,capture)
  for key,val in (('pci_candidates','n'),('displays',{})):
   v=evidence();v['device_map']['graphics']['value'][1][key]=val;panel_guard.refuse_active_panel_disable(DISABLED,v)
 def test_exact_active_panel_selected_for_disable_refused(self):
  with self.assertRaisesRegex(RuntimeError,'active internal panel'):panel_guard.refuse_active_panel_disable(DISABLED,evidence())
 def test_unbound_partial_ambiguous_and_legacy_not_promoted(self):
  cases=[]
  for key,val in [('status','unavailable'),('scan_status','failed')]:v=evidence();v['scan_binding'][key]=val;cases.append(v)
  v=evidence();v['device_map']['graphics']['status']='partial';cases.append(v)
  v=evidence();v['device_map']['graphics']['value'][1]['pci_candidates']=['n1','n2'];cases.append(v)
  v=evidence();v['device_map']['graphics']['value'].append(copy.deepcopy(v['device_map']['graphics']['value'][1]));cases.append(v)
  v=evidence();v['device_map']['graphics']['value'][1]['displays'][0].pop('routing_source');cases.append(v)
  for v in cases:panel_guard.refuse_active_panel_disable(DISABLED,v)
 def test_inactive_unavailable_nonpanel_subsystem_mismatch(self):
  for key in ('active','target_available','internal_panel'):
   v=evidence();v['device_map']['graphics']['value'][1]['displays'][0][key]=False;panel_guard.refuse_active_panel_disable(DISABLED,v)
  d=copy.deepcopy(DISABLED);next(iter(d.values()))['Subsystem ID']='99991043';panel_guard.refuse_active_panel_disable(d,evidence())
 def test_discrete_output_and_kept_intel_not_refused(self):
  graph=dm.build_graphics_map([NVIDIA,INTEL],[dict(PATH,target_luid=(0,11))],PNP);panel_guard.refuse_active_panel_disable(DISABLED,evidence(graph));panel_guard.refuse_active_panel_disable({},evidence())
class BeforeMutation(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  _,cls.utils=engine._load_engine()
  from Scripts.hardware_customizer import HardwareCustomizer
  from Scripts.config_prodigy import ConfigProdigy
  from Scripts.datasets import kext_data
  cls.customizer,cls.prodigy,cls.kexts=HardwareCustomizer,ConfigProdigy,kext_data
 def test_actual_upstream_emits_panel_disable(self):
  with redirect_stdout(io.StringIO()),patch.object(self.utils.Utils,'head'):cust,disabled,_=self.customizer().hardware_customization(copy.deepcopy(REPORT),'24.6.0')
  self.assertNotIn('Integrated adapter',cust['GPU']);self.assertIn('Integrated GPU: Integrated adapter',disabled)
  props=self.prodigy.deviceproperties(NS(utils=self.utils.Utils()),cust,disabled,'24.6.0',[NS(checked=False) for _ in self.kexts.kexts]);self.assertTrue(props['PciRoot(0x0)/Pci(0x2,0x0)']['disable-gpu'])
 def run_engine(self,mutate=False):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary);report=root/'Report.json';acpi=root/'ACPI';out=root/'out';token=scan_evidence.begin(root);scan_evidence.save_inventory(root,token,evidence());report.write_text(json.dumps(REPORT));acpi.mkdir();(acpi/'dsdt.aml').write_bytes(b'DSDT fixture');scan_evidence.finish(root,token,True)
   if mutate:report.write_text(json.dumps(dict(REPORT,unbound=True)))
   out.mkdir();(out/engine.MARKER).write_text('prior managed build');prior=out/'prior.efi';prior.write_bytes(b'prior EFI');later=Mock(side_effect=RuntimeError('later planning reached'))
   obj=NS(v=NS(validate_report=lambda _: (True,[],[],copy.deepcopy(REPORT))),h=self.customizer(),c=NS(check_compatibility=lambda _: (copy.deepcopy(REPORT),nullmoth.SEQUOIA,None)),ac=NS(dsdt=None,acpi=NS(acpi_tables=None),read_acpi_tables=lambda _:None,ensure_dsdt=lambda:True,select_acpi_patches=later),select_macos_version=lambda *a:'24.6.0',s=NS(select_smbios_model=lambda *a:'iMacPro1,1'))
   from p1401 import acpi_diagnostics,report as rm
   with redirect_stdout(io.StringIO()),patch.object(engine,'_load_engine',return_value=(NS(OCPE=lambda:obj),self.utils)),patch.object(engine,'_use_ock_cache'),patch.object(engine,'_nullmoth_gpu_pass'),patch.object(engine,'_wifi_prepass',side_effect=lambda hw,*a:hw),patch.object(acpi_diagnostics,'capture',return_value=nullcontext()),patch.object(rm,'normalized_copy',return_value=(str(report),[])):
    result=engine.build(str(report),str(acpi),str(out),download=True)
   return result,later.call_count,prior.exists()
 def test_bound_refusal_preserves_prior_efi_before_acpi_generation(self):
  result,calls,retained=self.run_engine();self.assertFalse(result.ok);self.assertIn('active internal panel',result.error);self.assertEqual(calls,0);self.assertTrue(retained)
 def test_modified_report_cannot_inherit_route(self):
  result,calls,_=self.run_engine(mutate=True);self.assertIn('later planning reached',result.error);self.assertEqual(calls,1)
if __name__=='__main__':unittest.main()
