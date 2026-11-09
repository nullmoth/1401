#!/usr/bin/env python3
"""Send logs attaches the AIR of functions the driver's translator refused, bounded and without following links.

The collector function is cut out of nullmoth-setup.sh between its begin/end markers and run on a temp folder tree.
"""
import os, pathlib, subprocess, sys, tempfile

root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[1])
text = (root / "Resources/nullmoth-setup.sh").read_text()
begin = text.index("# failed-air begin")
end = text.index("# failed-air end")
func = text[begin:end]
fails = 0


def check(name, ok, detail=""):
    global fails
    print(("ok   " if ok else "FAIL ") + name + (f" ({detail})" if detail else ""))
    fails += not ok


def run(src_files, extra=None):
    with tempfile.TemporaryDirectory() as t:
        t = pathlib.Path(t)
        src, dest = t / "src", t / "dest"
        src.mkdir(); dest.mkdir()
        for name, data in src_files.items():
            (src / name).write_bytes(data)
        if extra:
            extra(src, t)
        script = func + f'\ncollect_failed_air "{dest}" "" "{src}"\n'
        subprocess.run(["/bin/bash", "-c", script], check=True, capture_output=True)
        return sorted(p.name for p in dest.iterdir() if p.name.startswith("failed-air-")), (dest / "driver-state.txt").read_text()


names, state = run({"k-1.ll": b"; refusal\nx", "v-2.ll": b"y"})
check("each kept function is attached under a failed-air- name", names == ["failed-air-k-1.ll", "failed-air-v-2.ll"], names)
check("the state file says how many were attached", "failed-air: 2 file(s), 12 bytes" in state, state)

names, _ = run({f"f{i}.ll": b"a" for i in range(40)})
check("no more than 24 files are attached", len(names) == 24, len(names))

names, _ = run({"big.ll": b"a" * 600000, "ok.ll": b"a" * 100})
check("a function over 512 KB is left out, a small one kept", names == ["failed-air-ok.ll"], names)

names, _ = run({f"m{i}.ll": b"a" * 500000 for i in range(12)})
check("the total stays within 4 MB", len(names) == 8, len(names))


def link(src, t):
    secret = t / "secret"; secret.write_text("private")
    os.symlink(secret, src / "link.ll")


names, _ = run({"real.ll": b"a"}, link)
check("a link planted in the folder is not followed", names == ["failed-air-real.ll"], names)

names, _ = run({"we ird$name.ll": b"a"})
check("a file name is cut to plain characters", names == ["failed-air-we_ird_name.ll"], names)
# The copy itself must not follow a link or trust an earlier stat: a file swapped for a link between the shell tests and
# the read would otherwise be copied. The reader opens with O_NOFOLLOW and checks the open descriptor.
check("the copy opens without following links and checks the open descriptor",
      "O_NOFOLLOW" in func and "os.fstat(fd)" in func and 'cat "$f"' not in func)
with tempfile.TemporaryDirectory() as t:
    t = pathlib.Path(t); (t / "secret").write_text("secret"); os.symlink(t / "secret", t / "swapped.ll")
    reader = func[func.index("FA_READ='") + 9:]
    reader = reader[:reader.index("'\n")]
    r = subprocess.run(["/usr/bin/python3", "-I", "-c", reader, str(t / "swapped.ll")], capture_output=True)
    check("the reader refuses a link handed to it directly (the swapped-file case)", r.returncode != 0 and not r.stdout, r.returncode)

print("FAILED" if fails else "all arms pass")
sys.exit(1 if fails else 0)
