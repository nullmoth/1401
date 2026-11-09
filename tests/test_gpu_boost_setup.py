"""setup --gpu-boost: the boost script runs as root only from a package whose SHA256SUMS verified and names the script and
both daemon files; off and remove use the kept, root-owned copy; nothing is touched when the package is wrong."""
import hashlib
import os
import pathlib
import subprocess
import tarfile
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
T = (ROOT / "mac/Resources/nullmoth-setup.sh").read_text()
a = T.index('if [ -n "${GPUBOOST:-}" ]; then')
BLOCK = T[a:T.index('  cleanup; echo "RESULT ok"; exit 0\nfi\n', a) + len('  cleanup; echo "RESULT ok"; exit 0\nfi\n')]
STUB = '#!/bin/bash\necho "$@" >> "$CALLS"\n'


def package(listed=("boost_daemon.sh", "Library/NullMoth/boost/nvmtl-boost", "Library/NullMoth/boost/com.nullmoth.nvmtl-boost.plist"), tamper=False):
    d = pathlib.Path(tempfile.mkdtemp())
    root = d / "pkgroot"
    (root / "Library/NullMoth/boost").mkdir(parents=True)
    files = {"boost_daemon.sh": STUB, "Library/NullMoth/boost/nvmtl-boost": "bin", "Library/NullMoth/boost/com.nullmoth.nvmtl-boost.plist": "plist",
             "other": "x"}
    for n, c in files.items():
        (root / n).write_text(c)
    lines = [f"{hashlib.sha256((root / n).read_bytes()).hexdigest()}  {n}\n" for n in files if n in listed or n == "other"]
    (root / "SHA256SUMS").write_text("".join(lines))
    if tamper:
        (root / "boost_daemon.sh").write_text(STUB + "echo evil\n")
    tgz = d / "pkg.tar.gz"
    with tarfile.open(tgz, "w:gz") as t:
        t.add(root, arcname="pkgroot")
    return tgz, hashlib.sha256(tgz.read_bytes()).hexdigest()


def run(op, pkg=None, state=True, kept=None, sha=None):
    t = pathlib.Path(tempfile.mkdtemp())
    st = t / "ns"; st.mkdir()
    if state:
        (st / "state").write_text("x")
    if kept:
        (st / "boost_daemon.sh").write_text(STUB); (st / "boost_daemon.sh").chmod(0o755)
    calls = t / "calls"
    script = f'''stop() {{ echo "STOP $*"; exit 1; }}; step() {{ :; }}; ok() {{ echo "OK $*"; }}; cleanup() {{ :; }}
chown() {{ :; }}; stat() {{ case "$2" in %u) echo 0;; *) echo 755;; esac; }}
export CALLS={calls}; GPUBOOST={op}; ST={st}; STATE={st}/state; PKG={pkg[0] if pkg else ""}; SHA={sha or (pkg[1] if pkg else "")}
{BLOCK}'''
    p = subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True, timeout=60)
    return p.stdout, (calls.read_text().splitlines() if calls.exists() else []), st


class Boost(unittest.TestCase):
    def test_on_verifies_then_installs_and_switches_on_and_keeps_a_copy(self):
        out, calls, st = run("on", package())
        self.assertIn("OK GPU boost on", out, out)
        self.assertEqual([c.split()[0] for c in calls], ["install", "set"])
        self.assertEqual(calls[1], "set on")
        self.assertTrue((st / "boost_daemon.sh").is_file())

    def test_a_package_that_does_not_list_the_script_or_a_daemon_file_runs_nothing(self):
        for missing in ("boost_daemon.sh", "Library/NullMoth/boost/nvmtl-boost", "Library/NullMoth/boost/com.nullmoth.nvmtl-boost.plist"):
            listed = tuple(x for x in ("boost_daemon.sh", "Library/NullMoth/boost/nvmtl-boost", "Library/NullMoth/boost/com.nullmoth.nvmtl-boost.plist") if x != missing)
            out, calls, st = run("on", package(listed))
            self.assertIn("does not list", out, missing)
            self.assertEqual(calls, [])
            self.assertFalse((st / "boost_daemon.sh").exists())

    def test_a_script_changed_after_the_sums_were_made_or_a_wrong_package_hash_runs_nothing(self):
        out, calls, _ = run("on", package(tamper=True))
        self.assertIn("do not match its SHA256SUMS", out); self.assertEqual(calls, [])
        pkg = package()
        out, calls, _ = run("on", pkg, sha="0" * 64)
        self.assertIn("package checksum does not match", out); self.assertEqual(calls, [])

    def test_on_needs_the_driver_and_the_package(self):
        self.assertIn("not installed on this Mac", run("on", package(), state=False)[0])
        self.assertIn("needs the checked driver package", run("on", None)[0])

    def test_off_and_remove_use_the_kept_copy_and_nothing_else(self):
        out, calls, _ = run("off", kept=True)
        self.assertEqual(calls, ["set off"]); self.assertIn("OK GPU boost off", out)
        out, calls, st = run("remove", kept=True)
        self.assertEqual(calls, ["remove"]); self.assertFalse((st / "boost_daemon.sh").exists())

    def test_off_with_nothing_turned_on_here_changes_nothing(self):
        out, calls, _ = run("off")
        self.assertEqual(calls, []); self.assertIn("nothing to change", out)

    def test_an_unknown_action_is_refused(self):
        self.assertIn("takes on, off or remove", run("status")[0])


class Wiring(unittest.TestCase):
    def test_status_is_read_by_the_app_without_a_password_and_on_carries_the_package(self):
        swift = (ROOT / "mac/Sources/main.swift").read_text()
        self.assertIn('send("boostStatus"', swift)
        self.assertIn('"--gpu-boost", "on", "--pkg", pkg.path, "--sha", pkg.sha', swift)
        self.assertIn('extra: ["--gpu-boost", op]', swift)


if __name__ == "__main__":
    unittest.main()
