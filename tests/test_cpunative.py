"""Production adapter rejects arbitrary fields, identities, unverified helper paths and unbounded child output."""
import ctypes
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from p1401 import cpunative as cpu, job_guard, devicemap as dm


class CpuSchema(unittest.TestCase):
    def record(self):
        return {'schema':cpu.SCHEMA,'basic':{'vendor':'GenuineIntel','max_leaf':'0x1F'},'per_logical_processor':{'processors':[], 'affinity_restored':True},'truncated':False}
    def test_documented_fixture_shape_is_valid_but_extra_identifiers_are_not(self):
        data=self.record(); self.assertTrue(cpu.validate(data))
        for key,value in [('serial','private serial'),('name','private-host'),('error','C:/private-account')]:
            modified=dict(data);modified[key]=value;self.assertFalse(cpu.validate(modified))
        data['basic']['vendor']='privatevendor';self.assertFalse(cpu.validate(data))
    def test_numeric_depth_and_logical_caps_are_checked(self):
        data=self.record();data['per_logical_processor']['processors']=[{'group':0,'bit':0,'status':'measured'}]*513
        self.assertFalse(cpu.validate(data));data=self.record();data['leaf1']={'family':-1};self.assertFalse(cpu.validate(data))
        data=self.record();data['per_logical_processor']['processors']=[{'group':0,'bit':64}];self.assertFalse(cpu.validate(data))
    def test_adapter_has_no_caller_path_or_argument_surface_and_requires_job(self):
        with self.assertRaises(TypeError): cpu.cpu_native(path='untrusted')
        with patch.object(cpu.sys,'platform','win32'),patch.object(job_guard,'ready',return_value=False),patch.object(job_guard,'run_bounded',side_effect=AssertionError('launch')):
            with self.assertRaises(dm.ObservationUnavailable):cpu.cpu_native()
    def test_non_windows_does_not_launch(self):
        with patch.object(cpu.sys,'platform','nonwindows'),patch.object(job_guard,'run_bounded',side_effect=AssertionError('launch')):
            with self.assertRaises(dm.ObservationUnavailable):cpu.cpu_native()


class BoundedRunner(unittest.TestCase):
    def run_child(self,source,**options):
        real=subprocess.Popen
        def started(*args,**kwargs):
            process=real(*args,**kwargs)
            if not hasattr(process,'_handle'):process._handle=0
            return process
        with patch.object(job_guard,'ready',return_value=True),patch.object(job_guard,'contains',return_value=True),patch.object(job_guard.subprocess,'Popen',side_effect=started):
            return job_guard.run_bounded([sys.executable,'-I','-B','-c',source],**options)
    def test_stdout_and_stderr_are_capped_during_read(self):
        for stream in ['stdout','stderr']:
            data,code,reason=self.run_child('import sys; sys.'+stream+'.write("x"*3000000)',maximum=8192)
            self.assertEqual(data,b'');self.assertIn('bounded',reason)
    def test_hang_and_error_text_are_sanitized(self):
        data,code,reason=self.run_child('import time; time.sleep(30)',timeout=0.1)
        self.assertEqual(data,b'');self.assertIn('timed out',reason)
        data,code,reason=self.run_child('import sys;sys.stderr.write("private-host C:/private-account");sys.exit(9)')
        self.assertIn('exit 9',reason);self.assertNotIn('private',reason)
    def test_completed_output_is_bounded_and_available(self):
        data,code,reason=self.run_child('print("{}")')
        self.assertEqual(json.loads(data),{});self.assertEqual(code,0);self.assertIsNone(reason)
