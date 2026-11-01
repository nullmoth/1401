#!/usr/bin/env python3
"""Root must never write through a path that a program running as the user can swap.

1. Privileged.run: root writes a command's output into the user's temp folder and hands it back with chown. A symlink
   planted at output.txt made root truncate and fill the link's target, and chown gave that file to the user.
2. Driver update: a package from the newest release runs as root, so it needs a NullMoth signature, not only the
   SHA-256 listed in the same release.
3. setup --efi-read: root copied files straight into the user's folder (cp/echo through any symlink placed there).

Usage: test_root_writes_into_user_folders.py [mac-dir]   (default: the mac/ folder beside this file)
Arm 1 runs the shell template from Privileged.swift for real (as this user) against a planted symlink."""
import os
import pathlib
import re
import subprocess
import sys
import tempfile

MAC = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[1]
FAILS = []


def arm(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))
    if not ok:
        FAILS.append(name)


# 1. the output redirect and chown, run for real against a symlink planted where output.txt goes
priv = (MAC / "Sources/Privileged.swift").read_text()
m = re.search(r'let shell = "(.*?)"\n', priv)
arm("Privileged.swift has the root shell template", bool(m))
if m:
    tmpl = m.group(1).replace('\\"', '"').replace("\\\\", "\\")
    with tempfile.TemporaryDirectory() as d:
        victim = pathlib.Path(d, "victim.txt")
        victim.write_text("untouched\n")
        out = pathlib.Path(d, "run")
        out.mkdir()
        os.symlink(victim, out / "output.txt")
        q = lambda s: "'" + s.replace("'", "'\\''") + "'"   # noqa: E731  (the same quoting as the Swift)
        shell = (tmpl.replace("\\(command)", "echo planted-by-root")
                 .replace("\\(q(out.path))", q(str(out / "output.txt")))
                 .replace("\\(getuid())", str(os.getuid())))
        subprocess.run(["/bin/sh", "-c", shell], capture_output=True)
        arm("a symlink at output.txt is not written through (the link's target keeps its bytes)",
            victim.read_text() == "untouched\n", victim.read_text().strip())
    arm("chown never follows a link (-h)", "/usr/sbin/chown -h " in tmpl)

# 2. a newest-release driver package must verify against the release key before it is installed
main = (MAC / "Sources/main.swift").read_text()
pdf = main[main.find("private func processDriverFile"):]
pdf = pdf[:pdf.find("\n    }\n")]
arm("processDriverFile checks the release signature for a newest-release package",
    "plan.fromRelease" in pdf and "ReleaseSignature.verify(zip: loc" in pdf)
arm("the download and the chosen-file paths both mark the package as from the release",
    main.count("fromRelease: true, sig:") >= 2 or (main.count("fromRelease: true") >= 2 and "sig: l.sig" in main))
arm("the update check reads the package's .sig from the same release", 'n == pkg.1 + ".sig"' in main)

# 3. setup --efi-read writes nothing straight into the user's folder
setup = (MAC / "Resources/nullmoth-setup.sh").read_text()
blk = setup[setup.find('if [ -n "$EFIREAD" ]; then'):]
blk = blk[:blk.find("\nfi\n")]
direct = re.findall(r'(?:>|cp [^\n]*?)\s*"\$EFIREAD/[^"]*"', blk)
arm("--efi-read never cp/echo-writes into $EFIREAD directly", not direct, "; ".join(direct))
arm("--efi-read places its files with mv -h from a root-only folder", "mv -fh" in blk and "mktemp -d /private/var/tmp/" in blk)

print(f"{len(FAILS)} failed")
sys.exit(1 if FAILS else 0)
