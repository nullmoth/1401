import unittest
from p1401 import nullmoth


class LaptopDisplayNotes(unittest.TestCase):
    def report(self, compatibility=(None, None)):
        return {'GPU': {
            'RTX 4060 Mobile': {'Manufacturer': 'NVIDIA', 'Device Type': 'Discrete GPU', 'Device ID': '10DE-28A0'},
            'Intel integrated GPU': {'Manufacturer': 'Intel', 'Device Type': 'Integrated GPU', 'Compatibility': compatibility}},
            'Monitor': {'panel': {'Connector Type': 'Internal', 'Connected GPU': 'Intel integrated GPU'}}}

    def test_unsupported_panel_does_not_get_boot_or_wiring_guarantee(self):
        report = self.report()
        self.assertEqual(nullmoth.mark(report), ['RTX 4060 Mobile'])
        note = nullmoth.mux_help(report)
        self.assertIn('Some laptops have no MUX', note)
        self.assertIn('does not establish that the installer or accelerated desktop will work', note)
        self.assertNotIn('often HDMI', note)

    def test_supported_integrated_panel_is_not_described_as_unsupported(self):
        self.assertIsNone(nullmoth.mux_help(self.report(('24.99.99', '19.0.0'))))

    def test_panel_already_on_discrete_gpu_has_no_mux_notice(self):
        report = self.report()
        report['Monitor']['panel']['Connected GPU'] = 'RTX 4060 Mobile'
        self.assertIsNone(nullmoth.mux_help(report))


if __name__ == '__main__':
    unittest.main()
