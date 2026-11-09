"""Known-good evidence from the Mac side: what machines that reached the desktop were actually running.

The "reached the desktop" reports (sent by the Mac app after the first login) name the CPU, the Mac model (SMBIOS) the
EFI used, the display adapter's PCI ID, whether the NullMoth driver loaded and Metal ran. That is ground truth for what
worked, to compare the builder's choice against. This tool reduces the reports to a small committed table
(tests/corpus/known_good_desktop.json).

    python3 tools/machine_knowngood.py <intake folder>... [--write tests/corpus/known_good_desktop.json]
"""
import collections
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(HERE, "..", "tests", "corpus", "known_good_desktop.json")
FIELD = lambda text, name: (re.search(r"^" + re.escape(name) + r": (.*)$", text, re.M) or [None, None])[1]  # noqa: E731


def reduce(roots):
    """{'cpus': {cpu: {'n', 'models': {model: n}, 'macos': {major: n}}}, 'gpus': {pci id: {'n', 'driver', 'metal'}}}"""
    cpus = collections.defaultdict(lambda: {"n": 0, "models": collections.Counter(), "macos": collections.Counter()})
    gpus = collections.defaultdict(lambda: {"n": 0, "driver": 0, "metal": 0})
    files = 0
    for root in roots:
        for meta_path in glob.iglob(os.path.join(root, "*", "*.json")):
            try:
                if json.load(open(meta_path)).get("original_name") != "reached-desktop.txt":
                    continue
                text = open(meta_path[:-5] + ".txt", errors="replace").read()
            except (OSError, ValueError):
                continue
            files += 1
            cpu, model = FIELD(text, "cpu"), FIELD(text, "model")
            if not cpu or not model:
                continue
            mac = re.search(r"^macOS (\d+)\.", text, re.M)
            row = cpus[cpu.strip()]
            row["n"] += 1
            row["models"][model.strip()] += 1
            row["macos"][mac.group(1) if mac else "?"] += 1
            pci = re.match(r"(\w+:\w+)", FIELD(text, "display PCI") or "")
            if pci:
                g = gpus[pci.group(1).upper().replace(":", "-")]
                g["n"] += 1
                g["driver"] += (FIELD(text, "NVIDIA driver loaded (com.nullmoth)") or "").startswith("yes")
                g["metal"] += (FIELD(text, "Metal device") or "").startswith("yes")
    return {"cpus": {k: {"n": v["n"], "models": dict(v["models"]), "macos": dict(v["macos"])} for k, v in sorted(cpus.items())},
            "gpus": dict(sorted(gpus.items()))}, files


def load(path=DEFAULT_OUT):
    with open(path) as f:
        return json.load(f)


def main(argv):
    roots, write = [], None
    it = iter(argv)
    for a in it:
        if a == "--write":
            write = next(it)
        else:
            roots.append(a)
    if not roots:
        print(__doc__)
        return 2
    table, files = reduce(roots)
    print(f"{files} reached-desktop reports, {len(table['cpus'])} CPUs, {len(table['gpus'])} display adapters")
    if write:
        doc = {"schema": 1, "about": "Machines that reached the macOS desktop: CPU -> Mac model (SMBIOS) and macOS major, display "
               "adapter PCI id -> NullMoth driver loaded / Metal running (counts of reports).", **table}
        tmp = write + ".tmp"
        with open(tmp, "w") as f:
            json.dump(doc, f, indent=1, sort_keys=True)
        os.replace(tmp, write)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
