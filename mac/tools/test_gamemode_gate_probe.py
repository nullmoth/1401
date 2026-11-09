#!/usr/bin/env python3
"""gamemode_gate_probe.py finds the one function that answers the Game Mode question in the Intel slice of the game policy
daemon. Synthetic slices run anywhere; set NULLMOTH_TEST_GAMEPOLICYD to a copy of the daemon to check the real one."""
import importlib.util
import os
import struct
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("probe", os.path.join(HERE, "gamemode_gate_probe.py"))
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

OTHER = bytes.fromhex("554889E5" "B801000000" "5DC3")   # a function that answers yes, not the fixed no


def slice_with(callee, pad=64):
    body = b"\x90" * 16 + callee + b"\x90" * pad
    call_at = len(body)
    rel = 16 - (call_at + 5)
    body += b"\xE8" + struct.pack("<i", rel) + probe.AFTER_CALL + b"\x10" + b"\x90" * 16
    return body, call_at


class Gate(unittest.TestCase):
    def test_a_call_to_the_fixed_no_function_with_the_signature_is_found(self):
        body, call = slice_with(probe.CALLEE)
        self.assertEqual(probe.find_gate(body), [(call, 16)])

    def test_a_call_to_any_other_function_is_not_taken_for_it(self):
        body, _ = slice_with(OTHER)
        self.assertEqual(probe.find_gate(body), [])

    def test_the_signature_without_the_call_before_it_is_ignored(self):
        body = b"\x90" * 40 + probe.AFTER_CALL + b"\x10"
        self.assertEqual(probe.find_gate(body), [])

    def test_the_patch_is_two_bytes_inside_the_function(self):
        self.assertEqual(probe.CALLEE[4:6], bytes.fromhex("31C0"))

    def test_only_the_intel_slice_of_a_universal_file_is_read(self):
        body, _ = slice_with(probe.CALLEE)
        arm = b"\x00" * 64
        fat = struct.pack(">II", 0xCAFEBABE, 2) + struct.pack(">iiIII", 0x0100000C, 0, 0x1000, len(arm), 14) \
            + struct.pack(">iiIII", 0x01000007, 3, 0x2000, len(body), 14)
        data = fat + b"\0" * (0x1000 - len(fat)) + arm + b"\0" * (0x2000 - 0x1000 - len(arm)) + body
        off, sl = probe.x86_slice(data)
        self.assertEqual((off, sl), (0x2000, body))

    @unittest.skipUnless(os.environ.get("NULLMOTH_TEST_GAMEPOLICYD"), "set NULLMOTH_TEST_GAMEPOLICYD to a copy of the daemon")
    def test_the_real_daemon_has_exactly_one_gate(self):
        with open(os.environ["NULLMOTH_TEST_GAMEPOLICYD"], "rb") as f:
            _, sl = probe.x86_slice(f.read())
        self.assertEqual(len(probe.find_gate(sl)), 1)


if __name__ == "__main__":
    unittest.main()
