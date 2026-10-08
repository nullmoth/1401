"""Compile the production CPUID core against mixed-processor and bounded-affinity fixtures."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from p1401 import cpunative


class CpuCore(unittest.TestCase):
    def test_production_core_fixtures(self):
        repo=Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as directory:
            exe=Path(directory)/('cpu-fixtures.exe' if sys.platform=='win32' else 'cpu-fixtures')
            source=repo/'native/cpu/nm_cpuinfo_core.c';fixtures=repo/'tests/native/fixtures_cpuinfo.c'
            command=['cl','/nologo','/std:c11','/MT','/W4','/WX',str(source),str(fixtures),'/Fe:'+str(exe)] if sys.platform=='win32' else ['cc','-std=c11','-Wall','-Wextra','-Werror',str(source),str(fixtures),'-o',str(exe)]
            subprocess.run(command,cwd=directory,check=True,capture_output=True,timeout=30)
            subprocess.run([sys.executable,'-I','-B',str(repo/'tools/check_cpu_fixtures.py'),str(exe)],check=True,capture_output=True,timeout=30)
            rows=subprocess.check_output([str(exe)],timeout=30).splitlines()
            for line in rows:
                pieces=line.split(b'\t')
                if len(pieces)==3:
                    payload=json.loads(pieces[1])
                    self.assertTrue(cpunative.validate(payload),pieces[0].decode())
