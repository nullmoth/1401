#!/usr/bin/env python3
"""Finds, in the Intel slice of Apple's game policy daemon, the one function that answers "does this Mac support Game Mode".

The daemon asks four questions at start-up, in this order, and each answer is stored as a byte of its state object:
Game Mode, model-manager game assertions, dynamic power splitting, sustained execution. On the Intel slice the first is a
function that is only `xor eax,eax; ret` (a fixed "no"); the others ask MobileGestalt. The call that asks the first
question is recognised by what follows it: the answer is tested, and the preference ignoreDeviceRestrictions is read when it
is no. This tool locates that call and its target and prints the two bytes that would make the answer yes. It changes
nothing. usage: gamemode_gate_probe.py <gamepolicyd> [--json]"""
import json
import struct
import sys

CALL_THEN_TEST = bytes.fromhex("E8")            # call rel32
AFTER_CALL = bytes.fromhex("41B701" "41B401" "84C0" "75")   # mov r15b,1; mov r12b,1; test al,al; jne
CALLEE = bytes.fromhex("554889E5" "31C0" "5DC3")             # push rbp; mov rbp,rsp; xor eax,eax; pop rbp; ret


def x86_slice(data):
    magic = struct.unpack(">I", data[:4])[0]
    if magic in (0xCAFEBABE, 0xCAFEBABF):
        n = struct.unpack(">I", data[4:8])[0]
        for i in range(n):
            cpu, _sub, off, size, _al = struct.unpack(">iiIII", data[8 + 20 * i:28 + 20 * i])
            if cpu == 0x01000007:
                return off, data[off:off + size]
        return None
    if struct.unpack("<I", data[:4])[0] == 0xFEEDFACF and struct.unpack("<i", data[4:8])[0] == 0x01000007:
        return 0, data
    return None


def find_gate(slice_bytes):
    """[(call offset, callee offset)] of every call followed by the signature whose target is the fixed-no function."""
    out = []
    i = 0
    while True:
        i = slice_bytes.find(AFTER_CALL, i)
        if i < 0:
            return out
        call = i - 5
        if call >= 0 and slice_bytes[call:call + 1] == CALL_THEN_TEST:
            rel = struct.unpack("<i", slice_bytes[call + 1:call + 5])[0]
            target = call + 5 + rel
            if 0 <= target and slice_bytes[target:target + len(CALLEE)] == CALLEE:
                out.append((call, target))
        i += 1


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    data = open(argv[1], "rb").read()
    sl = x86_slice(data)
    if sl is None:
        print("no x86_64 slice")
        return 1
    base, body = sl
    gates = find_gate(body)
    if "--json" in argv:
        print(json.dumps([{"call": c, "callee": t, "patch_at": t + 4, "from": "31c0", "to": "b001"} for c, t in gates]))
    else:
        for c, t in gates:
            print(f"call at slice offset 0x{c:x} reaches the fixed-no function at 0x{t:x}; bytes 31 c0 at 0x{t + 4:x} (xor eax,eax) would become b0 01 (mov al,1)")
        if not gates:
            print("no gate found")
    return 0 if len(gates) == 1 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
