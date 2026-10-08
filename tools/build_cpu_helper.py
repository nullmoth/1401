"""Compile the reviewed x64 static-CRT helper and write its exact package pin; no runtime or release action."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def build(repo, destination):
    repo, destination = Path(repo).resolve(), Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    source = repo / 'native/cpu'
    exe = destination / 'nm_cpuinfo.exe'
    # Compiler intermediates are private build inputs, not runtime package files.
    with tempfile.TemporaryDirectory(prefix='1401-cpu-build-') as temporary:
        subprocess.run(['cl','/nologo','/std:c11','/O2','/MT','/W4','/WX','/DWIN32_LEAN_AND_MEAN','/D_WIN32_WINNT=0x0602',
                        str(source/'nm_cpuinfo_core.c'),str(source/'nm_cpuinfo_win.c'),'/Fe:'+str(exe),
                        '/link','/Brepro','/SUBSYSTEM:CONSOLE','kernel32.lib'],cwd=temporary,check=True,capture_output=True,timeout=45)
    output = subprocess.check_output(['dumpbin','/dependents',str(exe)],encoding='utf-8',errors='replace',timeout=15)
    dependencies = sorted({value.upper() for value in re.findall(r'^\s+(\S+\.dll)\s*$',output,re.M|re.I)})
    if dependencies != ['KERNEL32.DLL']: raise RuntimeError('Static CPU helper dependencies differ from the reviewed list.')
    digest = hashlib.sha256(exe.read_bytes()).hexdigest()
    pin = {'schema':'nullmoth-cpu-helper/1','sha256':digest,'dependencies':dependencies,'operation':'documented read-only CPUID allow-list'}
    (destination/'cpu-helper.json').write_text(json.dumps(pin,indent=2)+'\n',encoding='utf-8')
    return pin


if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--repo',required=True); parser.add_argument('--output',required=True)
    args=parser.parse_args(); print(json.dumps(build(args.repo,args.output)))
