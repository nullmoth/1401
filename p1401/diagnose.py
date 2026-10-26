"""What stopped a start from the 1401 stick, and what to do about it, in steps a person can follow.

python -m p1401.diagnose [--log opencore-*.txt ...] [--stopped "<the last line on the screen>"] [--report Report.json]

Reads the stick's OpenCore logs, the line the user says the screen stopped on, and (when there is one) this PC's scan.
Prints one block per finding ("  " lines) and a JSON summary on the last line:
  {"findings": [{"id", "title", "cause", "steps": [...], "rebuild": bool}], "cpu": "..."}
Every finding comes from failures in the stick logs and chats, and its steps are what got those machines past it.
The order is most specific first; nothing here changes a file.
"""
import argparse
import json
import re
import sys

from . import efi_rules, loc

CPU_LINE = re.compile(r"OCCPU: Found (.+)")

# Settings that every start from the stick needs; listed under each finding where they matter (Dortania, and the
# boards in MACHINES-WORKING.md).
BIOS_BASE = ["In the BIOS: CSM (Compatibility Support Module) Off, Secure Boot Off, Above 4G Decoding On.",
             "Save the BIOS settings, then start from the stick again and choose the 1401 entry."]


def facts(logs, report):
    """CPU family from the scan when there is one, else from the stick log's own CPU line."""
    name, vendor, laptop = "", "", None
    if report:
        cpu = report.get("CPU") or {}
        name, vendor = str(cpu.get("Processor Name") or ""), str(cpu.get("Manufacturer") or "")
        laptop = (report.get("Motherboard") or {}).get("Platform") == "Laptop"
        f = efi_rules.facts_from_report(report, "")
    else:
        for t in logs:
            m = CPU_LINE.search(t)
            if m:
                name = m.group(1).strip()
                break
        vendor = "AMD" if "AMD" in name else "Intel" if "Intel" in name else ""
        f = efi_rules.facts_from_report({"CPU": {"Manufacturer": vendor, "Processor Name": name, "Codename": ""}}, "")
    return {"name": name, "vendor": vendor, "laptop": laptop, "classes": set(f["cpu_class"])}


def handoff_steps(hw):
    """The freeze right after OpenCore hands over (EXITBS:START), by CPU family: what got those PCs past it."""
    steps = []
    if "intel_hybrid" in hw["classes"]:
        steps.append("Turn VT-d Off in the BIOS. On 12th-gen and newer Intel (Core Ultra included) this is what got "
                     "these PCs past EXITBS:START. If the BIOS hides VT-d, look on the Advanced or overclocking pages; on "
                     "some laptops (HONOR) it appears only after X2APIC is turned Off first.")
        steps.append("Also turn Off Kernel DMA Protection or Pre-boot DMA Protection if the BIOS lists them.")
        steps.append("If it still stops there, turn Hyper-Threading Off in the BIOS for the install, or turn the E-cores Off.")
    elif hw["vendor"] == "Intel":
        steps.append("Turn VT-d Off in the BIOS.")
        steps.append("Turn CFG Lock Off if the BIOS shows it.")
    elif hw["vendor"] == "AMD":
        steps.append("Turn IOMMU Off in the BIOS (often under AMD CBS > NBIO).")
        steps.append("Build the stick again with 1401 with this stick plugged in: the build reads this log and tries the "
                     "next memory settings for this board.")
    else:
        steps.append("Turn VT-d (Intel) or IOMMU (AMD) Off in the BIOS.")
    return steps + BIOS_BASE


def diagnose(logs, stopped="", report=None):
    hw = facts(logs, report)
    said = (stopped or "").lower()
    text = "\n".join(logs)
    out = []

    def add(fid, title, cause, steps, rebuild=False):
        out.append({"id": fid, "title": title, "cause": cause, "steps": steps, "rebuild": rebuild})

    # inside Apple's boot loader: no room in memory for the kernel (111 stick logs 10-23..10-26)
    if re.search(r"EB\.MM\.AKM|STOP 0x16|Couldn't allocate runtime area", text):
        add("no-room-for-kernel", "macOS could not find room in memory to start (EB.MM.AKM)",
            "Apple's boot loader stopped before macOS started: the memory map this PC's firmware gives it has no room "
            "for the kernel with the current settings. Starting the same stick again stops the same way.",
            ["Turn Above 4G Decoding On and CSM Off in the BIOS.",
             "Open 1401 on Windows with this stick plugged in and build again: the build reads this log and changes "
             "the memory settings for this PC.",
             "Write the stick and start from it."], rebuild=True)

    # firmware refused OpenCore's own drivers: Secure Boot is on (10 stick logs 10-23..10-26 end on this line)
    if re.search(r"OC: Driver \S+\.efi at \d+ cannot be loaded - Access Denied", text):
        add("secure-boot-on", "Secure Boot is on, so the PC refused OpenCore's drivers",
            "The firmware blocked the drivers OpenCore needs to read the macOS installer (Access Denied), so the "
            "installer cannot start.",
            ["Turn Secure Boot Off in the BIOS (on some boards: set OS Type to Other OS, or clear the Secure Boot keys).",
             "Save, start from the stick again, and choose the 1401 entry."])

    # the installer's file-system driver is not on the stick (built while GitHub was unreachable; 3 logs)
    if re.search(r"OC: Driver HfsPlus\.efi at \d+ cannot be found", text):
        add("hfsplus-missing", "The stick is missing a driver it needs to read the installer (HfsPlus.efi)",
            "The stick was built without HfsPlus.efi, usually because the download failed during the build.",
            ["Open 1401 on Windows with the internet connected and build the stick again.",
             "Write the stick and start from it."], rebuild=True)

    # the picker started Windows: the LAST start in the log is the Windows entry (type 32) and no Apple loader ran after it
    starts = list(re.finditer(r"OCB: Matching <>/\d+\[\d+\] args on type (\d+)|OCB: Perform boot Windows", text))
    chose_windows = starts and (starts[-1].group(1) in (None, "32")) and "AAPL:" not in text[starts[-1].end():]
    if chose_windows and not out:
        add("started-windows", "This start went to Windows, not the macOS installer",
            "In the OpenCore menu the Windows entry was chosen (or started by itself), so macOS never began.",
            ["Start from the stick again.", "In the OpenCore menu choose the entry named 1401 (the macOS installer), "
             "not Windows. If it is not listed, press the Space bar to show all entries."])

    if re.search(r"exitbs|exit bs", said) or ("exitbs:start" in said):
        add("froze-at-handoff", "The screen froze at EXITBS:START",
            "OpenCore handed over to macOS and the kernel never printed anything. On these PCs it is almost always a "
            "firmware setting that keeps a device in use across the hand-off.", handoff_steps(hw))

    if re.search(r"pci configuration|iopciconfigurator|^\s*pci\s*$", said):
        add("pci-configuration", "The start stopped at PCI configuration",
            "macOS hung while it mapped the PCI devices. This is the firmware's memory layout for PCI devices.",
            ["Turn Above 4G Decoding On in the BIOS.",
             "Turn Resizable BAR (Re-Size BAR) Support Off for the install.",
             "If it still stops there, open the stick's EFI/OC/config.plist and add npci=0x3000 to boot-args "
             "(NVRAM > Add > 7C436110-AB2A-4BBB-A880-FE41995C9F82 > boot-args)."] + BIOS_BASE)

    if re.search(r"black.*cursor|cursor.*black|黑屏|blackscreen", said):
        add("black-screen-cursor", "A black screen with only a mouse cursor after the install",
            "macOS has installed and started; the first-start setup screens are not drawing. Your Mac is working "
            "underneath.",
            ["Wait two minutes, then press Enter: on some PCs the setup screen is there but not drawn.",
             "Unplug every monitor but one, and plug that one into the graphics card's DisplayPort, then restart.",
             "If it stays black, send these logs with the line you typed, and post the report ID in the NullMoth "
             "Discord so the setup can be finished with you."])

    # "a kernel panic didn't occur, but ... a black screen" (typed 10-2x) is the black screen, not a panic
    typed_panic = re.search(r"panic|caplock|caps ?lock", said) and not any(f["id"] == "black-screen-cursor" for f in out)
    if typed_panic or re.search(r"panic-.*\.txt|Kernel trap at", text):
        add("kernel-panic", "macOS crashed while starting (kernel panic)",
            "The kernel stopped with an error. The stick saves the panic for 1401 to read.",
            ["Send these logs: the panic file on the stick names the driver that crashed. Post the report ID in the "
             "NullMoth Discord.",
             "Build the stick again with 1401 after sending: the build reads the stick's logs."] + BIOS_BASE[:1])

    if re.search(r"boot failure graphic|prohibited|startimage failed|systemimage abort", said):
        add("boot-refused", "Apple's boot loader refused to start macOS",
            "The prohibited sign (or 'boot failure') means boot.efi would not start this macOS on this setup.",
            ["Turn Secure Boot Off in the BIOS.",
             "Build the stick again with the newest 1401 (Check for updates first): it sets the Mac model and the "
             "Secure Boot model for this PC.",
             "Write the stick again and start from it."], rebuild=True)

    if re.search(r"no .*mac ?os.*(option|entry)|not has mac os|don.t see mac|only windows|"
                 r"(not|n.t) show.*mac ?os|boot into windows", said):
        add("no-macos-entry", "The OpenCore menu shows no macOS entry",
            "The installer is a recovery entry, which OpenCore can hide.",
            ["In the OpenCore menu, press the Space bar to show every entry, then choose 1401.",
             "If there is still none, the stick is not fully written: write it again with 1401."])

    # the installer lists no disk to install on: the firmware hides the drives behind RAID / Intel RST / VMD
    if re.search(r"sata|(no|n.t see|not see|missing).{0,20}(disk|drive|ssd|nvme)|硬盘|磁盘", said):
        add("no-disk-in-installer", "The installer does not show your disk",
            "macOS can only see drives the firmware presents as plain AHCI or NVMe disks. RAID, Intel RST and VMD hide them.",
            ["In the BIOS set SATA Mode to AHCI (not RAID or Intel RST).",
             "On Intel boards also turn VMD Controller Off.",
             "If Windows is installed on that disk, switch Windows to AHCI first (Microsoft's safe-mode steps), or Windows "
             "will not start afterwards.",
             "In the installer open Disk Utility, choose View > Show All Devices, and erase the disk you want as APFS."])

    if re.search(r"root device|waiting for root", said):
        add("waiting-for-root", "macOS is waiting for the USB stick (Still waiting for root device)",
            "macOS cannot see the USB port the stick is in.",
            ["Move the stick to a USB 2 port, or a USB port on the back of the PC, and start again.",
             "In the BIOS turn XHCI Hand-off On."])

    # nothing typed and the log reached the hand-off: say what the log can and cannot show, and how to make it useful
    if not out and "EXITBS:START" in text:
        add("after-handoff", "OpenCore handed over to macOS; what happened next is not in the log",
            "The stick's log ends where OpenCore gives control to macOS, which every start does. If the screen froze "
            "right there, these are the fixes that worked on PCs like this one; otherwise type the last line on the "
            "screen when you send logs, so 1401 can tell you exactly what to change.", handoff_steps(hw))
    return {"findings": out, "cpu": hw["name"]}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="1401 diagnose")
    ap.add_argument("--log", action="append", default=[])
    ap.add_argument("--stopped", default="")
    ap.add_argument("--report")
    a = ap.parse_args(argv)
    logs = []
    for p in a.log:
        try:
            with open(p, encoding="utf-8", errors="replace") as fh:
                logs.append(fh.read().replace("\0", ""))
        except OSError as e:
            print(f"  note: {p} could not be read ({e.strerror})")
    report = None
    if a.report:
        try:
            with open(a.report, encoding="utf-8") as fh:
                report = json.load(fh)
        except (OSError, ValueError) as e:
            print(f"  note: the scan report could not be read ({e}); the CPU comes from the log instead")
    result = diagnose(logs, a.stopped[:500], report)
    # the printed lines follow the app's language (A1401_LANG); the JSON line stays English for the upload and tests
    for f in result["findings"]:
        print("  " + loc.t(f["title"]))
        print("  " + loc.t(f["cause"]))
        for i, s in enumerate(f["steps"], 1):
            print(f"    {i}. {loc.t(s)}")
        print("  ")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
