"""The build says whether it used a real UTBMap or the generic UTBDefault (every port on, no map)."""
import unittest

from p1401 import utbmap


class Keat:
    def __init__(self, name, checked=True):
        self.name = name
        self.checked = checked


class Status(unittest.TestCase):
    def test_a_supplied_map_is_mapped(self):
        self.assertEqual(utbmap.map_status([Keat("USBToolBox"), Keat("UTBMap"), Keat("UTBDefault", False)]), "mapped")

    def test_the_generic_default_is_reported_as_default(self):
        self.assertEqual(utbmap.map_status([Keat("USBToolBox"), Keat("UTBDefault")]), "default")

    def test_a_disabled_default_without_a_map_is_none(self):
        self.assertEqual(utbmap.map_status([Keat("USBToolBox"), Keat("UTBDefault", False)]), "none")

    def test_the_real_matebook_build_is_default_not_mapped(self):
        # The EFI this project built for the MateBook has USBToolBox + UTBDefault and no UTBMap.kext.
        self.assertEqual(utbmap.map_status([Keat("USBToolBox"), Keat("UTBDefault"), Keat("XHCI-unsupported")]), "default")


if __name__ == "__main__":
    unittest.main()
