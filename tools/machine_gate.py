"""The replay gate: what the builder must satisfy for every PC the field has sent.

Input: the corpus (tools/machine_corpus.py) and one replay result per machine and macOS target (tools/machine_replay.py).
Output: per machine and target either SATISFIED, NAMED (refused for a reason the app explains in plain words) or a list of
violations. The target is zero violations.

Rules, each a named sentence so a failure reads as what is wrong:
  plan-or-named     the builder plans an EFI, or stops with one of the named reasons below, whose message is plain words
  device-explained  every device the builder leaves switched off is named (with its ID) in a note that says what to use instead
  smbios-known-good the Mac model matches one that machines with this CPU reached the desktop on
  storage-plan      a PC whose drives macOS cannot see gets a plan: the BIOS path and Windows preparation (VMD), or an external drive
  gpu-known-good    a card that most machines reached the desktop on with the NullMoth driver is planned for that driver
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

# name -> (matches the refusal text, what it means). Every refusal the field has produced is one of these.
NAMED = {
    "gpu-no-windows-driver": (r"only graphics card Windows reports",
                              "Windows has no driver for the card: install it in Windows and scan again"),
    "virtual-machine": (r"virtual machine's display adapter", "a virtual machine's display adapter: not a PC 1401 builds for"),
    "gpu-not-usable": (r"only graphics adapter in this PC is (?!.*virtual)", "a graphics chip macOS has no driver for"),
    "cpu-maker": (r"macOS runs only on Intel and AMD processors", "a processor macOS has no kernel support for (Zhaoxin)"),
    "no-gpu-driver": (r"macOS has no driver for this PC's graphics", "no graphics card macOS or the NullMoth driver can use"),
    "macos-not-offered": (r"This PC is capped at macOS", "the hardware tops out below the macOS the user picked"),
}
RAW = re.compile(r"Traceback|KeyError|NoneType|AttributeError|\[\"Root\.|\['Root\.|Unknown prompt|no rule answers")
NOTE_ONLY_FOR = {"Biometric": "Fingerprint or face sign-in"}


def refusal_code(text):
    return next((code for code, (rx, _) in NAMED.items() if re.search(rx, text)), None)


def plain(text):
    """The message after the exception class name must read as sentences, not as an engine dump."""
    body = re.sub(r"^\w+(Exit|Error|Loop|Offered): ", "", text).strip()
    return len(body) >= 40 and not RAW.search(body)


def notes_of(result):
    return [n for n in result.get("notices", []) if "\n" not in n]     # multi-line entries are the engine's transcript


def device_violations(machine, result):
    """Every non-graphics device the builder switched off must be named, by ID, in a note."""
    out = []
    notes = notes_of(result)
    joined = "\n".join(notes).upper()
    gpu_ids = {g.get("Device ID", "").upper() for g in machine["hardware"].get("GPU", [])}
    for section, did, name in result.get("disabled_detail", []):
        did = did.upper()
        if section == "GPU" or did in gpu_ids:
            if not any(n.startswith(("Graphics:", "NullMoth driver:")) or "basic display" in n for n in notes):
                out.append(f"device-explained: graphics {did} is switched off with no note")
            continue
        if section in NOTE_ONLY_FOR:
            if not any(n.startswith(NOTE_ONLY_FOR[section]) for n in notes):
                out.append(f"device-explained: {section} {name!r} is switched off with no note")
        elif did not in joined:
            out.append(f"device-explained: {section} {did} ({name}) is switched off with no note naming it")
    return out


def smbios_violation(machine, result, known):
    cpu = machine["hardware"]["CPU"].get("Processor Name", "").strip()
    row = known["cpus"].get(cpu)
    if not row or row["n"] < 25 or not result.get("smbios") or "0000" in cpu:   # "0000": the CPU has no model name
        return None
    seen = {m: n for m, n in row["models"].items() if n >= 3 and n / row["n"] >= 0.01}
    if result["smbios"] in seen:
        return None
    return f"smbios-known-good: {result['smbios']} for {cpu}; machines with this CPU reached the desktop on {sorted(seen)}"


def gpu_violation(machine, result, known):
    for g in machine["hardware"].get("GPU", []):
        row = known["gpus"].get(g.get("Device ID", "").upper())
        if not row or row["n"] < 10 or row["driver"] / row["n"] < 0.8 or g.get("Manufacturer") != "NVIDIA":
            continue
        if not any(n.startswith("NullMoth driver:") for n in result.get("notices", [])):
            return f"gpu-known-good: {g['Device ID']} reached the desktop with the NullMoth driver in {row['driver']} of {row['n']} reports, but the build does not plan it"
    return None


def storage_violation(machine, result):
    notes = notes_of(result)
    stor = [n for n in notes if n.startswith("Storage:")]
    plan = result.get("storage_plan") or {}
    if not stor and not plan:
        return None
    if not plan or not plan.get("steps"):
        return "storage-plan: a storage note without a plan"
    if plan["kind"] == "vmd-off" and not (plan.get("bios_path") and plan.get("controllers")):
        return "storage-plan: VMD plan without the BIOS path or the controllers"
    if not any(("VMD" in b or "macOS on a drive" in b) for b in result.get("bios", [])):
        return "storage-plan: the plan is not in the build's firmware requirements"
    return None


def evaluate(machine, result, known):
    """-> ('satisfied' | 'named', code) or ('violation', [messages])."""
    if not result["ok"]:
        text = result["refused"] or result["crash"]
        code = refusal_code(text)
        if code and plain(text):
            return "named", code
        return "violation", [f"plan-or-named: stopped without a named, plain reason: {text[:160]!r}"]
    bad = device_violations(machine, result)
    sv = storage_violation(machine, result)
    if sv:
        bad.append(sv)
    for fn in (smbios_violation, gpu_violation):
        v = fn(machine, result, known)
        if v:
            bad.append(v)
    return ("violation", bad) if bad else ("satisfied", None)


def summarize(machines, results, known, macos_list=("24", "25")):
    tally = {mv: {"satisfied": 0, "named": {}, "violations": 0} for mv in macos_list}
    offenders = []
    for m in machines:
        for mv in macos_list:
            kind, info = evaluate(m, results[m["key"]][mv], known)
            if kind == "satisfied":
                tally[mv]["satisfied"] += m["machines"]
            elif kind == "named":
                tally[mv]["named"][info] = tally[mv]["named"].get(info, 0) + m["machines"]
            else:
                tally[mv]["violations"] += m["machines"]
                offenders.append((m["key"], mv, info))
    return tally, offenders


def main(argv):
    import machine_corpus
    import machine_knowngood
    import machine_replay
    macos = ("24", "25")
    machines = machine_corpus.load()["machines"]
    known = machine_knowngood.load()
    results = machine_replay.run(machines, macos)
    tally, offenders = summarize(machines, results, known, macos)
    total = sum(m["machines"] for m in machines)
    for mv in macos:
        t = tally[mv]
        named = sum(t["named"].values())
        print(f"macOS {'15' if mv == '24' else '26'}: {total} machines  satisfied {t['satisfied']} "
              f"({100 * t['satisfied'] / total:.1f}%)  named reason {named} {t['named']}  violations {t['violations']}")
    for key, mv, info in offenders[:40]:
        print(key, mv, info)
    return 1 if offenders else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
