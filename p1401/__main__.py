"""python3 -m p1401 <command>

    plan  <Report.json> <ACPI dir> [--macos N]         what 1401 would build, no downloads
    build <Report.json> <ACPI dir> <out> [--macos N]   build + validate the EFI
"""
import argparse
import json
import sys

from . import engine, report


def _result_json(r):
    d = dict(r.__dict__)
    t = d.pop("transcript", None)
    if not r.ok and t:   # a failed build carries the engine's own printout, so the uploaded log shows what really went wrong
        d["transcript"] = t[-30000:]
    raw = d.pop("raw_hardware", None)
    d["hardware_summary"] = report.diagnostic_hardware(raw or d.pop("hardware", None))
    d.pop("hardware", None)
    d["decisions"] = [x.__dict__ for x in r.decisions]
    return d


def main(argv=None):
    ap = argparse.ArgumentParser(prog="1401")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "build"):
        p = sub.add_parser(name)
        p.add_argument("report")
        p.add_argument("acpi")
        if name == "build":
            p.add_argument("out")
        p.add_argument("--macos", default="")
        p.add_argument("--echo", action="store_true", help="show the engine's own output live")
        p.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    pol = engine.Policy(macos=a.macos)
    out = getattr(a, "out", None)
    if out is None:
        import tempfile  # noqa: PLC0415
        out = tempfile.mkdtemp(prefix="1401-plan-")
    r = engine.build(a.report, a.acpi, out, pol, echo=a.echo, download=(a.cmd == "build"))
    if a.json:
        print(json.dumps(_result_json(r), indent=2, default=str))
    else:
        print(f"{'OK' if r.ok else 'FAILED'}  macOS {r.macos_version}  SMBIOS {r.smbios}  OCLP={r.needs_oclp}")
        if r.error:
            print("error:", r.error)
        for d in r.decisions:
            print(f"  decided: {d.prompt!r} -> {d.answer!r}")
    return 0 if r.ok else 1


if __name__ == "__main__":
    sys.exit(main())
