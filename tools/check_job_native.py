"""Prove the owned kill-on-close worker also terminates a real descendant on Windows."""
import ctypes
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def verify_job_native(repo):
    with tempfile.TemporaryDirectory(prefix='1401-job-test-') as directory:
        receipt = Path(directory) / 'child.json'
        source = Path(repo) / 'p1401/job_guard.py'
        program = "import importlib.util,json,subprocess,sys,time; s=importlib.util.spec_from_file_location('guard',sys.argv[1]); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); assert m.initialize(); p=subprocess.Popen([sys.executable,'-I','-B','-c','import time; time.sleep(60)']); assert m.contains(p._handle); open(sys.argv[2],'w').write(json.dumps({'pid':p.pid,'contained':True})); time.sleep(60)"
        worker = subprocess.Popen([sys.executable, '-I', '-B', '-c', program, str(source), str(receipt)],
                                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        kernel = ctypes.WinDLL('kernel32.dll', winmode=0x800)
        kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int32, ctypes.c_uint32]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        kernel.WaitForSingleObject.restype = ctypes.c_uint32
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]; kernel.CloseHandle.restype = ctypes.c_int32
        child = None
        try:
            deadline = time.monotonic() + 5
            while not receipt.exists() and time.monotonic() < deadline and worker.poll() is None: time.sleep(0.01)
            data = json.loads(receipt.read_text())
            if data.get('contained') is not True: raise RuntimeError('Worker did not verify descendant job membership.')
            child = kernel.OpenProcess(0x100000, False, data['pid'])
            if not child: raise RuntimeError('Descendant process could not be observed.')
            if kernel.WaitForSingleObject(child, 0) != 0x102: raise RuntimeError('Descendant was not running before timeout simulation.')
            worker.kill(); worker.wait(timeout=2)
            if kernel.WaitForSingleObject(child, 2000) != 0: raise RuntimeError('Owned worker exit left its descendant running.')
        finally:
            if worker.poll() is None: worker.kill(); worker.wait(timeout=2)
            if child: kernel.CloseHandle(child)
    return {'owned_job_verified': True, 'descendant_terminated_on_worker_exit': True}
