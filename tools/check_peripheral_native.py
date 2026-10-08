"""Actual SDK positive/width-negative checks; host observations are performed only in the owned worker."""
import json
from pathlib import Path
import subprocess
import sys


def verify_peripheral_sdk(repo, directory):
    repo,directory=Path(repo).resolve(),Path(directory).resolve()
    positive,negative=directory/'peripheral-sdk.c',directory/'peripheral-sdk-negative.c'
    generator=repo/'tools/peripheral_sdk_check.py'
    for target,options in [(positive,[]),(negative,['--negative-boolean'])]:
        subprocess.run([sys.executable,'-I','-B',str(generator),str(target),*options],check=True,capture_output=True,timeout=10)
    exe=directory/'peripheral-sdk.exe'
    subprocess.run(['cl','/nologo','/std:c11','/TC',str(positive),'/Fe:'+str(exe),'/link','uuid.lib','ole32.lib'],
                   cwd=directory,check=True,capture_output=True,timeout=30)
    subprocess.run([str(exe)],check=True,capture_output=True,timeout=10)
    rejected=subprocess.run(['cl','/nologo','/std:c11','/c','/TC',str(negative)],cwd=directory,capture_output=True,timeout=30)
    errors=(rejected.stdout+rejected.stderr).decode('utf-8',errors='replace')
    if rejected.returncode==0 or 'C2338' not in errors or 'HidD_GetPreparsedData ctypes return width' not in errors:
        raise RuntimeError('BOOLEAN-width negative control was not rejected for the intended SDK mismatch.')
    for label, options in [('positive', []), ('negative', ['--negative-audio-guid'])]:
        source = directory / ('audio-guid-' + label + '.cpp')
        binary = directory / ('audio-guid-' + label + '.exe')
        subprocess.run([sys.executable, '-I', '-B', str(generator), str(source), '--guid-cpp', *options],
                       check=True, capture_output=True, timeout=10)
        subprocess.run(['cl', '/nologo', '/std:c++17', '/TP', str(source), '/Fe:' + str(binary)],
                       cwd=directory, check=True, capture_output=True, timeout=30)
        result = subprocess.run([str(binary)], capture_output=True, timeout=10)
        if result.returncode != (0 if label == 'positive' else 1):
            raise RuntimeError('SDK declared audio GUID check did not produce the expected result.')
    return {'actual_sdk_positive':True,'runtime_guids_and_hid_bitfield':True,
            'boolean_width_negative_rejected':True, 'audio_guid_negative_rejected':True}


def verify_cim_engine(repo, directory):
    destination=Path(directory)/'cim-engine-smoke.json'
    program="import json,sys;sys.path.insert(0,sys.argv[1]);from p1401 import job_guard,fwres;assert job_guard.initialize();result=fwres._cim_engine_smoke();open(sys.argv[2],'w').write(json.dumps(result))"
    subprocess.run([sys.executable,'-I','-B','-c',program,str(Path(repo).resolve()),str(destination)],
                   check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5)
    if not destination.is_file() or destination.stat().st_size>4096:raise RuntimeError('CIM engine verification evidence unavailable.')
    return json.loads(destination.read_bytes())
