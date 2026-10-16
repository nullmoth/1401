#!/usr/bin/env python3
"""A remove flag macOS cannot delete is cleared by OpenCore (user report 10-09: on a laptop whose firmware ignores
deletes made from macOS, the driver was removed 2 seconds after every login, install after install).

Runs the setup's real NVRAM Delete step against a stub nvram, in both directions: the flag present adds
nullmoth-remove to NVRAM > Delete; the flag absent adds nothing; an entry already there is not added twice."""
import os
import pathlib
import subprocess
import tempfile
import unittest

SETUP = pathlib.Path(__file__).resolve().parents[1] / "Resources/nullmoth-setup.sh"
START = 'del=$(plutil -extract NVRAM.Delete.$B xml1 -o - "$C" 2>/dev/null); DELADD=()'
END = "NEEDTOOL=0;"


def step():
    s = SETUP.read_text()
    assert s.count(START) == 1 and s.count(END) == 1, "anchors moved in nullmoth-setup.sh"
    return s[s.index(START):s.index(END)]


def run(flag, delete_list):
    t = tempfile.mkdtemp()
    stub = os.path.join(t, "nvram")
    with open(stub, "w") as f:
        f.write("#!/bin/bash\n" + ("echo \"$1\tseen\"; exit 0\n" if flag else "exit 1\n"))
    os.chmod(stub, 0o755)
    cfg = os.path.join(t, "config.plist")
    items = "".join(f"<string>{k}</string>" for k in delete_list)
    with open(cfg, "w") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?><plist version="1.0"><dict><key>NVRAM</key><dict><key>Delete</key><dict>'
                f'<key>7C436110-AB2A-4BBB-A880-FE41995C9F82</key><array>{items}</array></dict></dict></dict></plist>')
    script = (f'PATH="{t}:/usr/bin:/bin"; B=7C436110-AB2A-4BBB-A880-FE41995C9F82; C="{cfg}"\n' + step() +
              '\nprintf "%s\\n" "${DELADD[@]}"\n')
    r = subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return [l for l in r.stdout.splitlines() if l and not l.startswith("CHANGE")]


class StaleRemoveFlag(unittest.TestCase):
    def test_a_flag_still_set_at_install_is_handed_to_opencore_to_delete(self):
        self.assertEqual(run(True, ["boot-args", "csr-active-config"]), ["nullmoth-remove"])

    def test_no_flag_adds_nothing_so_the_picker_tool_keeps_its_restart_path(self):
        self.assertEqual(run(False, ["boot-args", "csr-active-config"]), [])

    def test_an_entry_already_in_the_config_is_not_added_twice(self):
        self.assertEqual(run(True, ["boot-args", "csr-active-config", "nullmoth-remove"]), [])


if __name__ == "__main__":
    unittest.main()
