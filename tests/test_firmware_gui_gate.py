"""Qualification requires the actual packaged WinForms firmware fixture result."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('package_firmware_gate', ROOT / 'tools/check_windows_package.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FirmwareGuiGate(unittest.TestCase):
    def test_actual_completed_fixture_is_accepted(self):
        MODULE.require_firmware_navigation({'firmware_prerequisite_navigation': True,
                                             'firmware_navigation_fixture_phase': 'complete'})

    def test_old_missing_false_or_nonboolean_fixture_is_refused(self):
        for value in [None, False, 1, 'true']:
            with self.subTest(value=value):
                with self.assertRaises(RuntimeError):
                    MODULE.require_firmware_navigation({'firmware_prerequisite_navigation': value,
                                                         'firmware_navigation_fixture_phase': 'complete'})
        with self.assertRaises(RuntimeError): MODULE.require_firmware_navigation({})

    def test_incomplete_or_missing_phase_is_refused(self):
        for phase in [None, '', 'scan_next_return', 'unbuilt_usb_refusal']:
            with self.subTest(phase=phase):
                with self.assertRaises(RuntimeError):
                    MODULE.require_firmware_navigation({'firmware_prerequisite_navigation': True,
                                                         'firmware_navigation_fixture_phase': phase})


if __name__ == '__main__': unittest.main()
