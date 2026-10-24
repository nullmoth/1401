#!/usr/bin/env python3
"""The kernel log query from the boot time can run into its cap on a PC whose clock moved during the boot (dual boot
with Windows: "Wall Clock adjustment detected"). It then runs once more bounded by the boot itself (--last boot)."""
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
source = (ROOT / "Resources/nullmoth-setup.sh").read_text()
helper = 'lshow() {' + source.split('lshow() {', 1)[1].split('# Copy newest files', 1)[0]
helper = helper.replace('/usr/bin/log show', 'log show')
fn = '  kernel_log_since_boot() {' + source.split('  kernel_log_since_boot() {', 1)[1].split('\n  }\n', 1)[0] + '\n  }\n'
fails = 0


def arm(name, ok, detail=""):
    global fails
    fails += not ok
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f" ({detail.strip()[-300:]})"))


def run(stub):
    with tempfile.TemporaryDirectory() as d:
        bin_ = pathlib.Path(d) / "bin"
        bin_.mkdir()
        (bin_ / "log").write_text("#!/bin/bash\n" + stub)
        os.chmod(bin_ / "log", 0o755)
        script = helper + "\nboot=$(date +%s)\n" + fn + "kernel_log_since_boot 1 3; echo \"rc=$?\"\n"
        p = subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True, timeout=30,
                           env=dict(os.environ, PATH=f"{bin_}:/usr/bin:/bin"))
        return p.stdout + p.stderr


# the clock-based query never answers; the boot-bounded one does
out = run('case " $* " in *" --last boot "*) echo "NVRM: GSP boot fixture"; exit 0;; esac\nexec sleep 20\n')
arm("a query cut off at its cap runs again bounded by the boot", "retrying from this boot's start" in out, out)
arm("and the retry's kernel lines reach the file", "NVRM: GSP boot fixture" in out and "rc=0" in out, out)
# an answer within the cap is never queried twice
out = run('case " $* " in *" --last boot "*) echo "SECOND QUERY"; exit 0;; esac\necho "NVRM: first answer"; exit 0\n')
arm("an answered query is not repeated", "NVRM: first answer" in out and "SECOND QUERY" not in out and "rc=0" in out, out)
# a query that fails for another reason keeps its own exit status (the file records it)
out = run('case " $* " in *" --last boot "*) echo "SECOND QUERY"; exit 0;; esac\nexit 3\n')
arm("another failure is reported, not retried", "rc=3" in out and "SECOND QUERY" not in out, out)
print(f"{fails} failed")
sys.exit(1 if fails else 0)
