"""The Ryzen laptop power-limit option, as a build notice.

A Ryzen laptop under macOS runs at the firmware's default power limits. After macOS is installed, the Mac app can set a
quieter battery profile through NullMoth's RyzenAdj build (mac/Resources/nullmoth-ryzen-power.sh), which needs the
opt-in NMSMN kext and the boot argument nmsmn=1. This module only says so before the build; it changes no config, adds no
kext and sets no boot argument. Zen-family laptops only: the SMU mailboxes the kext allows exist from Zen 1 on; the
scan names the CPU, not the family, so the notice goes to AMD CPUs whose name says Ryzen.
"""
import re

_RYZEN = re.compile(r"\bRyzen\b", re.I)

NOTE = ("Power: this laptop has a Ryzen processor. After macOS is installed, the Mac app can apply a quieter battery "
        "power-limit profile with NullMoth's RyzenAdj build. It is off unless you turn it on: it needs the NMSMN kernel "
        "extension and nmsmn=1 in the boot arguments, runs as a root job, and only changes limits the processor accepts.")


def applies(report):
    hw = report or {}
    cpu, board = hw.get("CPU") or {}, hw.get("Motherboard") or {}
    return (cpu.get("Manufacturer") == "AMD" and bool(_RYZEN.search(str(cpu.get("Processor Name") or "")))
            and board.get("Platform") == "Laptop")


def notes(report):
    return [NOTE] if applies(report) else []
