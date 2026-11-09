#!/usr/bin/env python3
"""Send logs attaches the AIR of functions the driver's translator refused: bounded, and never through a link.

The collector is cut out of nullmoth-setup.sh between its begin/end markers and run on a temp folder tree. An optional
argument names another copy of the setup script (the previous version) to show the arms fail on it.
"""
import os, pathlib, subprocess, sys, tempfile

here = pathlib.Path(__file__).resolve().parents[1]
script = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else here / "Resources/nullmoth-setup.sh"
text = script.read_text()
func = text[text.index("# failed-air begin"):text.index("# failed-air end")]
NEW = "fa_read" in func     # the previous collector took 3 arguments and had no descriptor-based reader
fails = 0


def check(name, ok, detail=""):
    global fails
    print(("ok   " if ok else "FAIL ") + name + (f" ({detail})" if detail else ""))
    fails += not ok


def run(src_files, setup=None, prelude=""):
    with tempfile.TemporaryDirectory() as t:
        t = pathlib.Path(t)
        src, dest = t / "src", t / "dest"
        src.mkdir(); dest.mkdir()
        (t / "secret").write_text("PRIVATE-SECRET")
        for name, data in src_files.items():
            (src / name).write_bytes(data)
        if setup:
            setup(src, t)
        args = f'"{dest}" "" "" "{src}"' if NEW else f'"{dest}" "" "{src}"'
        body = func + prelude.replace("@SRC@", str(src)).replace("@SECRET@", str(t / "secret")) + f"\ncollect_failed_air {args}\n"
        subprocess.run(["/bin/bash", "-c", body], check=True, capture_output=True)
        kept = {p.name: p.read_bytes() for p in dest.iterdir() if p.name.startswith("failed-air-")}
        state = (dest / "driver-state.txt").read_text()
        return kept, state


kept, state = run({"k-1.ll": b"; refusal\nx", "v-2.ll": b"y"})
check("each kept function is attached under a failed-air- name", sorted(kept) == ["failed-air-k-1.ll", "failed-air-v-2.ll"], sorted(kept))
check("the state file says how many were attached", "failed-air: 2 file(s), 12 bytes" in state, state)

kept, _ = run({f"f{i}.ll": b"a" for i in range(40)})
check("no more than 24 files are attached", len(kept) == 24, len(kept))

kept, _ = run({"big.ll": b"a" * 524289, "edge.ll": b"a" * 524288, "ok.ll": b"a" * 100})
check("a file over 512 KiB is left out, one at the limit and a small one are kept", sorted(kept) == ["failed-air-edge.ll", "failed-air-ok.ll"], sorted(kept))

kept, _ = run({f"m{i}.ll": b"a" * 500000 for i in range(12)})
check("the total stays within 4 MB", len(kept) == 8, len(kept))

kept, _ = run({"real.ll": b"a"}, lambda src, t: os.symlink(t / "secret", src / "link.ll"))
check("a link in the folder is not followed", sorted(kept) == ["failed-air-real.ll"] and all(b"PRIVATE" not in v for v in kept.values()), sorted(kept))

kept, _ = run({"we ird$name.ll": b"a"})
check("a file name is cut to plain characters", sorted(kept) == ["failed-air-we_ird_name.ll"], sorted(kept))

# The race: any stat of a file in the folder swaps that file for a link to a private file, as an attacker could between
# a check and the read. Reading through a descriptor opened without following links never returns the private file.
kept, _ = run({"swap.ll": b"ordinary"}, prelude='stat() { case "$*" in *"@SRC@"*) ln -sf "@SECRET@" "@SRC@/swap.ll";; esac; command stat "$@"; }\n')
check("a file swapped for a link after it was checked does not leak the private file", all(b"PRIVATE" not in v for v in kept.values()), {k: v[:20] for k, v in kept.items()})

# a file that is not what it was named: a link planted before the run, pointing at a large private file
kept, _ = run({}, lambda src, t: (t / "secret").write_bytes(b"PRIVATE" * 100000) or os.symlink(t / "secret", src / "huge.ll"))
check("a link to an oversized file yields nothing", not kept, sorted(kept))
print("FAILED" if fails else "all arms pass")
sys.exit(1 if fails else 0)
