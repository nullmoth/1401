"""Runs `python -m p1401 <args>` for the replay tools with one change that is about this host, not the builder: macOS refuses to
run the unsigned ocvalidate that OpenCore ships (the process is killed), so the already hash-verified copy is ad-hoc signed
into a temporary file and that file is run. The product code and its integrity checks are untouched."""
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from p1401 import __main__ as cli, validate  # noqa: E402

if sys.platform == "darwin":
    _orig = validate.ocvalidate_path

    def _signed():
        verified = _orig()
        signed = os.path.join(tempfile.mkdtemp(prefix="1401-oc-"), "ocvalidate")
        shutil.copyfile(verified, signed)
        os.chmod(signed, 0o755)
        subprocess.run(["codesign", "-s", "-", "--force", signed], capture_output=True, check=False)
        return signed

    validate.ocvalidate_path = _signed

sys.exit(cli.main(sys.argv[1:]))
