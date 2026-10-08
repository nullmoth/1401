"""Capture failures must preserve raw PCI evidence without hanging the build."""
import ctypes
import json
import struct
import sys
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from p1401 import hwcapture as hc


class CaptureSafety(unittest.TestCase):
    def worker(self, source, timeout=2):
        return hc._bounded_native([sys.executable, '-I', '-B', '-c', source], timeout=timeout)

    def test_stalled_worker_is_killed_with_raw_inventory_preserved(self):
        before = time.monotonic()
        native = self.worker('import time; time.sleep(30)', timeout=0.1)
        self.assertLess(time.monotonic() - before, 3)
        self.assertEqual(native['nvidia']['status'], 'unavailable')
        report = {'GPU': {'Fixture Radeon': {'Device ID': '1002-1638', 'ACPI Path': '\\_SB.PCI0.VGA'}}}
        with patch.object(hc.sys, 'platform', 'win32'), patch.object(hc, '_bounded_native', return_value=native):
            result = hc.collect(report)
        self.assertEqual(result['gpus'][0]['device_id'], '1002-1638')
        self.assertEqual(result['gpus'][0]['raytracing']['status'], 'unavailable')

    def test_worker_crash_and_invalid_or_large_output_are_unavailable(self):
        sources = ['raise SystemExit(4)',
                   'import sys; open(sys.argv[1],"w").write("[]")',
                   'import sys; open(sys.argv[1],"w").write("x" * 262145)']
        for source in sources:
            result = self.worker(source)
            self.assertEqual(result['nvidia']['status'], 'unavailable')
            self.assertEqual(result['nvidia']['devices'], [])

    def test_real_isolated_worker_protocol(self):
        result = hc._bounded_native()
        self.assertEqual(set(result), {'cpu_topology', 'nvidia'})
        self.assertIn('devices', result['nvidia'])
        self.assertNotIn('traceback', json.dumps(result).lower())

    def test_short_record_cannot_read_next_record_as_its_affinity(self):
        malformed = struct.pack('<II', 0, 8) + struct.pack('<II', 4, 64) + bytes(56)
        with self.assertRaises(ValueError): hc.parse_topology(malformed)
        with self.assertRaises(ValueError): hc.parse_topology(b'abc')
        with self.assertRaises(ValueError):
            hc.parse_topology(struct.pack('<II', 0, 32) + bytes(22) + struct.pack('<H', 2))

    def test_numa_extended_record_is_preserved(self):
        buf = struct.pack('<II', 6, 64) + struct.pack('<I', 1) + bytes(18) + struct.pack('<H', 2)
        buf += struct.pack('<QH6x', 3, 0) + struct.pack('<QH6x', 1, 1)
        self.assertEqual(hc.parse_topology(buf)['numa_nodes'], 1)

    def test_trust_always_closes_state_offline_and_uses_pinned_handle(self):
        for status in (0, -1):
            actions = []
            def verify(hwnd, action, data):
                d = ctypes.cast(data, ctypes.POINTER(hc.TrustData)).contents
                actions.append(d.dwStateAction)
                self.assertEqual(d.dwUIChoice, 2)
                self.assertTrue(d.dwProvFlags & 0x1000)
                self.assertEqual(d.pFile.contents.hFile, 123)
                return status
            ok = hc.authenticode_ok('fixture.dll', handle=123, trust=SimpleNamespace(WinVerifyTrust=verify))
            self.assertEqual(ok, status == 0)
            self.assertEqual(actions, [1, 2])

    def test_exception_still_closes_trust_state(self):
        calls = []
        def verify(hwnd, action, data):
            state = ctypes.cast(data, ctypes.POINTER(hc.TrustData)).contents.dwStateAction
            calls.append(state)
            if state == 1: raise OSError('fixture provider failed')
            return 0
        with self.assertRaises(OSError):
            hc.authenticode_ok('fixture.dll', trust=SimpleNamespace(WinVerifyTrust=verify))
        self.assertEqual(calls, [1, 2])

    def test_raw_inventory_bounds_and_unknown_status(self):
        result = hc.gpu_inventory({'GPU': {'Fixture': {'Device ID': [], 'ACPI Path': 'x' * 513}}})
        self.assertIsNone(result[0]['device_id']); self.assertIsNone(result[0]['acpi_path'])
        self.assertIn('no usable PCI identity', result[0]['kind'])
        self.assertEqual(ctypes.sizeof(hc.NvmlPciInfo), 68)
        self.assertEqual(hc.FileInfo.hFile.offset, 16)
        self.assertEqual(hc.TrustData.hWVTStateData.offset, 56)
        self.assertEqual(ctypes.sizeof(hc.TrustData), 88)


if __name__ == '__main__': unittest.main()
