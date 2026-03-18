"""Tests for SerialProxy config parsing"""

import unittest
from unittest.mock import patch, MagicMock

import serial

from ser2tcp.serial_proxy import SerialProxy


def _mock_init(self, config=None, log=None):
    """Mock init that sets required attributes for __del__"""
    self._servers = []
    self._serial = None


def _make_port_info(device, vid=None, pid=None, serial_number=None,
        manufacturer=None, product=None, location=None):
    """Create mock ListPortInfo"""
    info = MagicMock()
    info.device = device
    info.vid = vid
    info.pid = pid
    info.serial_number = serial_number
    info.manufacturer = manufacturer
    info.product = product
    info.location = location
    return info


class TestFixSerialConfig(unittest.TestCase):
    """Test serial config normalization"""

    def _make_proxy(self):
        """Helper to create SerialProxy with mocked __init__"""
        proxy = SerialProxy.__new__(SerialProxy)
        _mock_init(proxy)
        return proxy

    def test_parity_none(self):
        proxy = self._make_proxy()
        config = {'port': '/dev/ttyUSB0', 'parity': 'NONE'}
        result = proxy.fix_serial_config(config)
        self.assertEqual(result['parity'], serial.PARITY_NONE)

    def test_parity_even(self):
        proxy = self._make_proxy()
        config = {'port': '/dev/ttyUSB0', 'parity': 'EVEN'}
        result = proxy.fix_serial_config(config)
        self.assertEqual(result['parity'], serial.PARITY_EVEN)

    def test_parity_odd(self):
        proxy = self._make_proxy()
        config = {'port': '/dev/ttyUSB0', 'parity': 'ODD'}
        result = proxy.fix_serial_config(config)
        self.assertEqual(result['parity'], serial.PARITY_ODD)

    def test_stopbits_one(self):
        proxy = self._make_proxy()
        config = {'port': '/dev/ttyUSB0', 'stopbits': 'ONE'}
        result = proxy.fix_serial_config(config)
        self.assertEqual(result['stopbits'], serial.STOPBITS_ONE)

    def test_stopbits_two(self):
        proxy = self._make_proxy()
        config = {'port': '/dev/ttyUSB0', 'stopbits': 'TWO'}
        result = proxy.fix_serial_config(config)
        self.assertEqual(result['stopbits'], serial.STOPBITS_TWO)

    def test_bytesize_eightbits(self):
        proxy = self._make_proxy()
        config = {'port': '/dev/ttyUSB0', 'bytesize': 'EIGHTBITS'}
        result = proxy.fix_serial_config(config)
        self.assertEqual(result['bytesize'], serial.EIGHTBITS)

    def test_bytesize_sevenbits(self):
        proxy = self._make_proxy()
        config = {'port': '/dev/ttyUSB0', 'bytesize': 'SEVENBITS'}
        result = proxy.fix_serial_config(config)
        self.assertEqual(result['bytesize'], serial.SEVENBITS)

    def test_config_without_parity(self):
        """Config without parity should remain unchanged"""
        proxy = self._make_proxy()
        config = {'port': '/dev/ttyUSB0', 'baudrate': 115200}
        result = proxy.fix_serial_config(config)
        self.assertNotIn('parity', result)
        self.assertEqual(result['baudrate'], 115200)

    def test_unknown_parity_unchanged(self):
        """Unknown parity value should remain unchanged"""
        proxy = self._make_proxy()
        config = {'port': '/dev/ttyUSB0', 'parity': 'UNKNOWN'}
        result = proxy.fix_serial_config(config)
        self.assertEqual(result['parity'], 'UNKNOWN')


class TestSerialProxyConfigMaps(unittest.TestCase):
    """Test config mapping dictionaries"""

    def test_parity_config_keys(self):
        expected = {'NONE', 'EVEN', 'ODD', 'MARK', 'SPACE'}
        self.assertEqual(set(SerialProxy.PARITY_CONFIG.keys()), expected)

    def test_stopbits_config_keys(self):
        expected = {'ONE', 'ONE_POINT_FIVE', 'TWO'}
        self.assertEqual(set(SerialProxy.STOPBITS_CONFIG.keys()), expected)

    def test_bytesize_config_keys(self):
        expected = {'FIVEBITS', 'SIXBITS', 'SEVENBITS', 'EIGHTBITS'}
        self.assertEqual(set(SerialProxy.BYTESIZE_CONFIG.keys()), expected)


class TestFindPortByMatch(unittest.TestCase):
    """Test USB device matching"""

    def _make_proxy(self):
        proxy = SerialProxy.__new__(SerialProxy)
        _mock_init(proxy)
        return proxy

    @patch('ser2tcp.serial_proxy._list_ports.comports')
    def test_match_by_vid_pid(self, mock_comports):
        mock_comports.return_value = [
            _make_port_info('/dev/ttyUSB0', vid=0x303A, pid=0x4001),
        ]
        proxy = self._make_proxy()
        result = proxy.find_port_by_match({'vid': '0x303A', 'pid': '0x4001'})
        self.assertEqual(result, '/dev/ttyUSB0')

    @patch('ser2tcp.serial_proxy._list_ports.comports')
    def test_match_by_serial_number(self, mock_comports):
        mock_comports.return_value = [
            _make_port_info('/dev/ttyUSB0', vid=0x303A, serial_number='ABC123'),
        ]
        proxy = self._make_proxy()
        result = proxy.find_port_by_match({'serial_number': 'ABC123'})
        self.assertEqual(result, '/dev/ttyUSB0')

    @patch('ser2tcp.serial_proxy._list_ports.comports')
    def test_match_wildcard(self, mock_comports):
        mock_comports.return_value = [
            _make_port_info(
                '/dev/ttyUSB0', vid=0x303A, manufacturer='Espressif Systems'),
        ]
        proxy = self._make_proxy()
        result = proxy.find_port_by_match({'manufacturer': 'Espressif*'})
        self.assertEqual(result, '/dev/ttyUSB0')

    @patch('ser2tcp.serial_proxy._list_ports.comports')
    def test_match_case_insensitive(self, mock_comports):
        mock_comports.return_value = [
            _make_port_info('/dev/ttyUSB0', vid=0x303A, product='USB Device'),
        ]
        proxy = self._make_proxy()
        result = proxy.find_port_by_match({'product': 'usb*'})
        self.assertEqual(result, '/dev/ttyUSB0')

    @patch('ser2tcp.serial_proxy._list_ports.comports')
    def test_match_no_device_found(self, mock_comports):
        mock_comports.return_value = [
            _make_port_info('/dev/ttyUSB0', vid=0x1234, pid=0x5678),
        ]
        proxy = self._make_proxy()
        with self.assertRaises(ValueError) as ctx:
            proxy.find_port_by_match({'vid': '0x303A'})
        self.assertIn('No device found', str(ctx.exception))

    @patch('ser2tcp.serial_proxy._list_ports.comports')
    def test_match_multiple_devices(self, mock_comports):
        mock_comports.return_value = [
            _make_port_info('/dev/ttyUSB0', vid=0x303A, pid=0x4001),
            _make_port_info('/dev/ttyUSB1', vid=0x303A, pid=0x4001),
        ]
        proxy = self._make_proxy()
        with self.assertRaises(ValueError) as ctx:
            proxy.find_port_by_match({'vid': '0x303A'})
        self.assertIn('Multiple devices', str(ctx.exception))

    def test_match_empty_criteria(self):
        proxy = self._make_proxy()
        with self.assertRaises(ValueError) as ctx:
            proxy.find_port_by_match({})
        self.assertIn('cannot be empty', str(ctx.exception))

    def test_match_unknown_attribute(self):
        proxy = self._make_proxy()
        with self.assertRaises(ValueError) as ctx:
            proxy.find_port_by_match({'unknown': 'value'})
        self.assertIn('Unknown match attribute', str(ctx.exception))

    @patch('ser2tcp.serial_proxy._list_ports.comports')
    def test_match_filters_none_values(self, mock_comports):
        """Devices with None for matched attribute should not match"""
        mock_comports.return_value = [
            _make_port_info('/dev/ttyUSB0', vid=None, pid=None),
            _make_port_info('/dev/ttyUSB1', vid=0x303A, pid=0x4001),
        ]
        proxy = self._make_proxy()
        result = proxy.find_port_by_match({'vid': '0x303A'})
        self.assertEqual(result, '/dev/ttyUSB1')


class TestFixSerialConfigMatch(unittest.TestCase):
    """Test fix_serial_config with match"""

    def _make_proxy(self):
        proxy = SerialProxy.__new__(SerialProxy)
        _mock_init(proxy)
        return proxy

    def test_config_requires_port_or_match(self):
        proxy = self._make_proxy()
        with self.assertRaises(ValueError) as ctx:
            proxy.fix_serial_config({})
        self.assertIn("'port' or 'match'", str(ctx.exception))

    @patch('ser2tcp.serial_proxy._list_ports.comports')
    def test_config_with_match(self, mock_comports):
        mock_comports.return_value = [
            _make_port_info('/dev/ttyUSB0', vid=0x303A, pid=0x4001),
        ]
        proxy = self._make_proxy()
        config = {'match': {'vid': '0x303A'}}
        result = proxy.fix_serial_config(config)
        self.assertEqual(result['port'], '/dev/ttyUSB0')
        self.assertNotIn('match', result)


if __name__ == "__main__":
    unittest.main()
