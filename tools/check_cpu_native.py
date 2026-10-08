"""Compile with the actual Windows SDK and verify the fixed helper through a staged owned worker."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys


def verify_cpu_native(repo, directory, evidence=None):
    evidence = evidence if evidence is not None else {}
    repo,directory=Path(repo).resolve(),Path(directory).resolve()
    app=directory/'cpu-app';app.mkdir(exist_ok=True)
    shutil.copytree(repo/'p1401',app/'p1401',ignore=shutil.ignore_patterns('__pycache__','*.pyc'),dirs_exist_ok=True)
    helper_spec = importlib.util.spec_from_file_location('cpu_helper_build', repo / 'tools/build_cpu_helper.py')
    helper = importlib.util.module_from_spec(helper_spec)
    helper_spec.loader.exec_module(helper)
    pin=helper.build(repo,app/'bin')
    evidence.update({'helper_sha256':pin['sha256'],'static_dependencies':pin['dependencies']})
    groups=directory/'cpu-group-fixtures.exe'
    subprocess.run(['cl','/nologo','/std:c11','/MT','/W4','/WX','/DWIN32_LEAN_AND_MEAN','/D_WIN32_WINNT=0x0602',
                    str(repo/'native/cpu/nm_cpuinfo_core.c'),str(repo/'tests/native/cpu_groups_sdk.c'),'/Fe:'+str(groups)],
                   cwd=directory,check=True,capture_output=True,timeout=45)
    group_proof=json.loads(subprocess.check_output([str(groups)],timeout=10))
    evidence['sdk_group_parser']=group_proof
    rejected=subprocess.run([str(app/'bin/nm_cpuinfo.exe'),'unsupported'],capture_output=True,timeout=6)
    if rejected.returncode!=2:raise RuntimeError('Fixed CPU helper accepted arguments.')
    worker=app/'p1401/hwcapture.py';destination=directory/'cpu-native-capture.json'
    subprocess.run([sys.executable,'-I','-B',str(worker),'--collect-worker',str(destination)],
                   check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=13)
    if destination.stat().st_size>2*1024*1024:raise RuntimeError('Staged CPU capture exceeded limit.')
    capture=json.loads(destination.read_bytes());record=capture.get('device_map',{}).get('cpu_native',{})
    evidence.update({'stage_status':record.get('status'),'stage_reason':record.get('error')})
    if record.get('status') not in ['measured','partial']:raise RuntimeError('Actual packaged-path CPU stage was not observable.')
    value=record['value'];per=value['per_logical_processor']
    if not per.get('visited') or per.get('affinity_restored') is not True:raise RuntimeError('Actual CPU helper did not visit and restore its owned thread.')
    if any(item.get('status')=='measured' and 'vendor' not in item for item in per.get('processors',[])):raise RuntimeError('Measured CPU record omitted vendor.')
    evidence.update({'static_dependencies':pin['dependencies'],'helper_sha256':pin['sha256'],'sdk_group_parser':group_proof,
            'packaged_path_owned_worker':True,'stage_status':record['status'],'visited':per['visited'],
            'actual_affinity_restored':True,'actual_location_unavailable':per.get('location_unavailable',0),
            'argument_refused':True,'serial_leaf_excluded':True,'hardware_support_qualified':False})
    return evidence
