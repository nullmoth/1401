"""Compile and run the production Windows local-report lifecycle fixtures."""
from pathlib import Path
import argparse,json,os,subprocess,tempfile

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    root=Path(__file__).resolve().parent.parent
    result={'ok':False,'scope':'production local diagnostic save/reopen/launch-failure fixtures; no network, USB writes or installation'}
    try:
        if os.name!='nt':raise RuntimeError('Windows compilation and runtime required')
        # Use the known OS directory API instead of an environment-provided executable path.
        import ctypes
        buf=ctypes.create_unicode_buffer(32768)
        n=ctypes.windll.kernel32.GetWindowsDirectoryW(buf,len(buf))
        if not n or n>=len(buf):raise RuntimeError('Windows directory unavailable')
        compiler=Path(buf.value)/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
        with tempfile.TemporaryDirectory(prefix='report-lifecycle-') as folder:
            exe=Path(folder)/'report-fixture.exe'
            compiled=subprocess.run([str(compiler),'/nologo','/warnaserror+','/target:exe','/out:'+str(exe),'/r:System.Windows.Forms.dll','/r:System.Web.Extensions.dll',str(root/'windows/App/DurableReport.cs'),str(root/'windows/App/Engine.cs'),str(root/'tests/native/ReportReliability.cs')],capture_output=True,timeout=30)
            if compiled.returncode:
                import re
                result['compiler_codes']=sorted(set(re.findall(r'\b(?:CS\d+)\b',(compiled.stdout+compiled.stderr).decode(errors='replace'))))
                raise RuntimeError('Compiled fixture failed')
            run=subprocess.run([str(exe)],capture_output=True,timeout=20)
            result['runtime_exit']=run.returncode
            if run.returncode:raise RuntimeError('Production lifecycle fixture failed')
            result['fixture']=json.loads(run.stdout)
            result['ok']=True
    except Exception as error:result['failure_type']=type(error).__name__
    Path(args.output).parent.mkdir(parents=True,exist_ok=True);Path(args.output).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));return 0 if result['ok'] else 1
if __name__=='__main__':raise SystemExit(main())
