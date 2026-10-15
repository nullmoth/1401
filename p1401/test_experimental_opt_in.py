#!/usr/bin/env python3
"""The experimental community drivers are OFF unless the user turns them on, and the build still says they exist.

Two community drivers can be added to a build: AMDRadeonRDNA4 (RX 9070 display) and SimpleMtkWlan (MediaTek Wi-Fi).
Both are unproven on most of the hardware they claim and both take over something the machine needs to be usable -- the
display and the network. Added silently, either one can turn a machine that installs fine into a machine with no
picture or no internet, which is worse than the plain firmware framebuffer and Ethernet. So the gate is:

  off (default): the kext is NOT added, and a notice names the driver and how to ask for it
  on:            the kext IS added, with the honest warning

This drives the real apply_kexts() functions with a stubbed engine dataset and asserts both directions. The negative
control is the pre-gate source (*.bak-expdrv), which must add the kext with no opt-in at all -- if that control stops
firing, the test is no longer measuring the gate.
"""
import importlib.machinery
import importlib.util
import pathlib
import shutil
import subprocess
import sys
import tempfile
import types

HERE = pathlib.Path(__file__).resolve().parent
fails = 0


def check(name, ok, detail=""):
    global fails
    print(("ok   " if ok else "FAIL ") + name + (f" ({detail})" if detail else ""))
    fails += not ok


class FakeKextManager:
    def __init__(self):
        self.checked = []

    def check_kext(self, idx, macos_version):
        self.checked.append(idx)


class FakeOcpe:
    def __init__(self):
        self.k = FakeKextManager()


def install_fake_dataset(kext_names):
    """Stand in for the upstream engine's Scripts.datasets.kext_data, which is only importable inside a real build."""
    kext_data = types.ModuleType("Scripts.datasets.kext_data")
    kext_data.kexts = list(kext_names)
    kext_data.kext_index_by_name = {n: i for i, n in enumerate(kext_names)}
    scripts = sys.modules.setdefault("Scripts", types.ModuleType("Scripts"))
    datasets = sys.modules.setdefault("Scripts.datasets", types.ModuleType("Scripts.datasets"))
    datasets.kext_data = kext_data
    scripts.datasets = datasets
    sys.modules["Scripts.datasets.kext_data"] = kext_data


def load(path, name):
    """Load one module file on its own, so the pre-gate .bak copies can be driven beside the current ones.

    The loader is named explicitly: the control files end in .bak-expdrv, and importlib infers no loader for a
    suffix it does not know, so without this the control could not run at all.
    """
    spec = importlib.util.spec_from_file_location(name, path,
                                                  loader=importlib.machinery.SourceFileLoader(name, str(path)))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


NAVI48 = {"GPU": {"Radeon RX 9070": {"Device ID": "1002-7550"}}}
MT7922 = {"Network": {"MediaTek Wi-Fi": {"Device ID": "14C3-7922"}}}


def run(mod_path, name, hardware, kext_name, **kw):
    """Drive one apply_kexts and report (kext was added, the notices it wrote)."""
    install_fake_dataset([kext_name])
    mod = load(mod_path, name)
    ocpe, notices = FakeOcpe(), []
    mod.apply_kexts(ocpe, hardware, (24, 0, 0), notices, **kw)
    return bool(ocpe.k.checked), notices


def mentions_opt_in(notices):
    return any("experimental drivers" in n.lower() for n in notices)


# --- AMD RDNA 4 display driver ---
added, notices = run(HERE / "amd_rdna4.py", "t_amd_off", NAVI48, "AMDRadeonRDNA4")
check("RX 9070: the display driver is NOT added by default", not added)
check("RX 9070: the default build still says the driver exists and how to ask for it", mentions_opt_in(notices))

added, notices = run(HERE / "amd_rdna4.py", "t_amd_on", NAVI48, "AMDRadeonRDNA4", experimental=True)
check("RX 9070: turning experimental drivers on adds it", added)

added, _ = run(HERE / "amd_rdna4.py", "t_amd_other", {"GPU": {"RX 580": {"Device ID": "1002-67DF"}}},
               "AMDRadeonRDNA4", experimental=True)
check("a non-Navi-48 AMD card never gets this kext, even with experimental on", not added)

# --- MediaTek Wi-Fi ---
added, notices = run(HERE / "netsupport.py", "t_net_off", MT7922, "SimpleMtkWlan")
check("MT7922: the Wi-Fi driver is NOT added by default", not added)
check("MT7922: the default build still says the driver exists and how to ask for it", mentions_opt_in(notices))

added, notices = run(HERE / "netsupport.py", "t_net_on", MT7922, "SimpleMtkWlan", experimental=True)
check("MT7922: turning experimental drivers on adds it", added)

# --- the opt-in defaults to off in the policy the app and CLI both construct ---
sys.path.insert(0, str(HERE.parent))
from p1401 import engine  # noqa: E402

check("Policy() defaults experimental_drivers to off", engine.Policy().experimental_drivers is False)

# --- negative control: the pre-gate source added both kexts with no opt-in ---
# Read from the commit before the gate rather than from a .bak file beside the source: a stray backup can be deleted
# or edited and the control would quietly stop measuring anything. PRE_GATE is the merge that release-2.0 sat on when
# the gate went in.
PRE_GATE = "a451dd7"
tmp = pathlib.Path(tempfile.mkdtemp(prefix="1401-expdrv-control-"))
for fn, name, hardware, kext in (("amd_rdna4.py", "c_amd", NAVI48, "AMDRadeonRDNA4"),
                                 ("netsupport.py", "c_net", MT7922, "SimpleMtkWlan")):
    old = subprocess.run(["git", "-C", str(HERE.parent), "show", f"{PRE_GATE}:p1401/{fn}"],
                         capture_output=True, text=True)
    if old.returncode:
        print(f"FAIL negative control for {fn}: could not read it at {PRE_GATE} - the control is UNKNOWN, not clean")
        fails += 1
        continue
    src = tmp / fn
    src.write_text(old.stdout)
    added, _ = run(src, name, hardware, kext)
    check(f"negative control: {fn} at {PRE_GATE} added {kext} with no opt-in", added)
shutil.rmtree(tmp, ignore_errors=True)

sys.exit(1 if fails else 0)
