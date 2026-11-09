#!/usr/bin/env python3
"""An update must not switch the boot picker's hidden auxiliary entries back on (1401 #371). The first install still stops
the hiding so the Remove entry is reachable; once the install record says that was done, a later HideAuxiliary=true is the
user's choice. The Remove entry stays non-auxiliary either way, so it is still on the picker."""
import pathlib
import plistlib
import subprocess
import tempfile
import unittest

SETUP = pathlib.Path(__file__).resolve().parents[1] / "Resources/nullmoth-setup.sh"
TEXT = SETUP.read_text()


def between(start, end):
    a = TEXT.index(start)
    return TEXT[a:TEXT.index(end, a) + len(end)]


FUNCS = between("has() {", "\nget() {")[:-len("\nget() {")] + "\n" + between("get() {", "; }\n") + "\n" \
    + between("picker_edits() {", "    i=$((i+1)); done; }")
KEEP = [l for l in TEXT.splitlines() if l.startswith("KEEP_USER_HIDEAUX=0;")][0]


def edits(hide, keep, aux=False):
    t = tempfile.mkdtemp()
    cfg = pathlib.Path(t, "config.plist")
    cfg.write_bytes(plistlib.dumps({"Misc": {"Boot": {"HideAuxiliary": hide, "ShowPicker": True, "PickerMode": "Builtin"},
                                               "Tools": [{"Path": "NullMothSafe.efi", "Auxiliary": aux, "TextMode": True}]}}))
    out = subprocess.run(["/bin/bash", "-c", FUNCS + f'\nKEEP_USER_HIDEAUX={keep}\npicker_edits {cfg}'],
                         capture_output=True, text=True, timeout=30)
    return out.stdout.split()


def keep_flag(state_text):
    t = tempfile.mkdtemp()
    st = pathlib.Path(t, "state")
    if state_text is not None:
        st.write_text(state_text)
    out = subprocess.run(["/bin/bash", "-c", f'STATE={st}\n{KEEP}\necho $KEEP_USER_HIDEAUX'], capture_output=True, text=True, timeout=30)
    return out.stdout.strip()


class KeepsHiddenAuxiliary(unittest.TestCase):
    def test_the_first_install_still_stops_the_hiding(self):
        self.assertEqual(edits(True, 0), ["Misc.Boot.HideAuxiliary|-bool|false"])

    def test_an_update_after_an_install_that_unhid_leaves_the_users_choice(self):
        self.assertEqual(edits(True, 1), [])

    def test_the_remove_entry_is_still_made_visible_when_the_hiding_stays(self):
        self.assertEqual(edits(True, 1, aux=True), ["Misc.Tools.0.Auxiliary|-bool|false"])

    def test_the_record_decides(self):
        self.assertEqual(keep_flag("SET_HIDEAUX=1\nOLD_HIDEAUX=true\n"), "1")
        self.assertEqual(keep_flag("SET_HIDEAUX=0\n"), "0")
        self.assertEqual(keep_flag(None), "0")


if __name__ == "__main__":
    unittest.main()
