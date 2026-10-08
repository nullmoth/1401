"""Device identity must survive early build failure without serials or network credentials."""
import unittest
from p1401.report import diagnostic_hardware, normalize
from p1401 import nullmoth

class HardwareDiagnostics(unittest.TestCase):
    def test_early_build_identity(self):
        report = {'CPU': {'Manufacturer': 'AMD', 'Processor Name': 'Ryzen 5 7500F', 'Core Count': 6, 'Serial': 'private'},
                  'Motherboard': {'Name': 'B650MT-E PRO', 'Chipset': 'B650', 'Serial Number': 'private'},
                  'GPU': {'Basic Display Adapter': {'Manufacturer': 'NVIDIA', 'Device ID': '10DE-2B85', 'Device Type': 'Discrete GPU', 'Serial': 'private'}},
                  'Network': {'RTL8125': {'Device ID': '10EC-8125', 'MAC': 'private', 'WiFi Password': 'private'}},
                  'Monitor': {'Panel': {'Connected GPU': 'Basic Display Adapter', 'Connector Type': 'Internal', 'Serial': 'private'}}}
        result = diagnostic_hardware(report)
        self.assertEqual(result['GPU'][0]['Device ID'], '10DE-2B85')
        self.assertEqual(result['Motherboard']['Name'], 'B650MT-E PRO')
        self.assertEqual(result['CPU']['Core Count'], 6)
        self.assertNotIn('private', str(result))
        self.assertEqual(result['Network'][0]['Device ID'], '10EC-8125')

    def test_known_cards_without_windows_driver(self):
        for pid in ('2B85', '2B87', '2B8C', '2C18', '2C58', '2D05', '1F06', '2484', '2803'):
            report, _ = normalize({'GPU': {'Basic Display Adapter': {'Manufacturer': 'Unknown', 'Device Type': 'Discrete GPU', 'Device ID': '10DE-' + pid}}})
            self.assertTrue(nullmoth.supported(report['GPU']['Basic Display Adapter']), pid)
            self.assertEqual(nullmoth.mark(report), ['Basic Display Adapter'])
        report, _ = normalize({'GPU': {'Basic Display Adapter': {'Manufacturer': 'Unknown', 'Device Type': 'Discrete GPU', 'Device ID': '10DE-1B80'}}})
        self.assertFalse(nullmoth.supported(report['GPU']['Basic Display Adapter']))

    def test_missing_sections(self):
        self.assertEqual(diagnostic_hardware(None), {})
        self.assertEqual(diagnostic_hardware({'GPU': None, 'CPU': []}), {})

if __name__ == '__main__':
    unittest.main()
