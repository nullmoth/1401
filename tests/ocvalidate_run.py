"""One way for the tests to run OpenCore's validator. macOS on Apple silicon kills (SIGKILL) a binary whose signature is missing or
invalid, so the zip's copy is written to a private temp folder and, if the OS kills it, signed ad hoc there and run again. A run
that is killed even then says so: a validator killed by the OS is not a validation failure."""
import hashlib
import os
import subprocess
import sys
import tempfile

KILLED = (-9, 137)
_ready = {}


def run_validator(tool, config, timeout=60):
    """tool: the validator's bytes (from the OpenCore zip); config: path to a config.plist. -> CompletedProcess (text)."""
    key = hashlib.sha256(tool).hexdigest()
    exe = _ready.get(key)
    if exe is None or not os.path.isfile(exe):
        exe = os.path.join(tempfile.mkdtemp(prefix="ocvalidate-"), "ocvalidate")
        with open(exe, "wb") as fh:
            fh.write(tool)
        os.chmod(exe, 0o755)
        _ready[key] = exe
    p = subprocess.run([exe, config], capture_output=True, text=True, timeout=timeout)
    if p.returncode in KILLED and sys.platform == "darwin":
        sign = subprocess.run(["codesign", "-s", "-", "-f", exe], capture_output=True, text=True, timeout=60)
        p = subprocess.run([exe, config], capture_output=True, text=True, timeout=timeout)
        if p.returncode in KILLED:
            raise AssertionError("validator killed by the OS (SIGKILL) even after ad-hoc signing (codesign said: "
                                 + ((sign.stderr or sign.stdout).strip()[:200] or "nothing") + ")")
    elif p.returncode in KILLED:
        raise AssertionError("validator killed by the OS (SIGKILL)")
    return p
