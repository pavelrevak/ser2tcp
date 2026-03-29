"""Tests for SerialProxy config parsing"""

import unittest
from unittest.mock import patch, MagicMock

import serial

from ser2tcp.serial_proxy import SerialProxy


def _mock_init(self, config=None, log=None):
    """Mock init that sets required attributes for __del__"""
    self._servers = []
    self._serial = None
    self._reader_thread = None
    self._reader_sock_r = None
    self._reader_sock_w = None
    self._reader_running = False


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
        result = proxy._init_serial_config(config)
        self.assertEqual(result['parity'], serial.PARITY_NONE)

    def test_parity_even(self):
        proxy = self._make_proxy()
        config = {'port': '/dev/ttyUSB0', 'parity': 'EVEN'}
        result = proxy._init_serial_config(config)
        self.assertEqual(result['parity'], serial.PARITY_EVEN)

    def test_parity_odd(self):
        proxy = self._make_proxy()
        config = {'port': '/dev/ttyUSB0', 'parity': 'ODD'}
        result = proxy._init_serial_config(config)
        self.assertEqual(result['parity'], serial.PARITY_ODD)

    def test_stopbits_one(self):
        proxy = self._make_proxy()
        config = {'port': '/dev/ttyUSB0', 'stopbits': 'ONE'}
        result = proxy._init_serial_config(config)
        self.assertEqual(result['stopbits'], serial.STOPBITS_ONE)

    def test_stopbits_two(self):
        proxy = self._make_proxy()
        config = {'port': '/dev/ttyUSB0', 'stopbits': 'TWO'}
        result = proxy._init_serial_config(config)
        self.assertEqual(result['stopbits'], serial.STOPBITS_TWO)

    def test_bytesize_eightbits(self):
        proxy = self._make_proxy()
        config = {'port': '/dev/ttyUSB0', 'bytesize': 'EIGHTBITS'}
        result = proxy._init_serial_config(config)
        self.assertEqual(result['bytesize'], serial.EIGHTBITS)

    def test_bytesize_sevenbits(self):
        proxy = self._make_proxy()
        config = {'port': '/dev/ttyUSB0', 'bytesize': 'SEVENBITS'}
        result = proxy._init_serial_config(config)
        self.assertEqual(result['bytesize'], serial.SEVENBITS)

    def test_config_without_parity(self):
        """Config without parity should remain unchanged"""
        proxy = self._make_proxy()
        config = {'port': '/dev/ttyUSB0', 'baudrate': 115200}
        result = proxy._init_serial_config(config)
        self.assertNotIn('parity', result)
        self.assertEqual(result['baudrate'], 115200)

    def test_unknown_parity_unchanged(self):
        """Unknown parity value should remain unchanged"""
        proxy = self._make_proxy()
        config = {'port': '/dev/ttyUSB0', 'parity': 'UNKNOWN'}
        result = proxy._init_serial_config(config)
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


class TestInitSerialConfigMatch(unittest.TestCase):
    """Test _init_serial_config with match"""

    def _make_proxy(self):
        proxy = SerialProxy.__new__(SerialProxy)
        _mock_init(proxy)
        return proxy

    def test_config_requires_port_or_match(self):
        proxy = self._make_proxy()
        with self.assertRaises(ValueError) as ctx:
            proxy._init_serial_config({})
        self.assertIn("'port' or 'match'", str(ctx.exception))

    def test_config_with_match_filtered(self):
        proxy = self._make_proxy()
        config = {'match': {'vid': '0x303A'}, 'baudrate': 115200}
        result = proxy._init_serial_config(config)
        self.assertNotIn('match', result)
        self.assertEqual(result['baudrate'], 115200)


class TestSerialProxyName(unittest.TestCase):
    """Test port name property"""

    @patch('ser2tcp.serial_proxy._server.Server')
    def test_name_from_config(self, _mock_server):
        proxy = SerialProxy(
            {'name': 'gate2a', 'serial': {'port': '/dev/ttyUSB0'},
             'servers': [{'protocol': 'tcp', 'address': '0.0.0.0',
                 'port': 10001}]})
        self.assertEqual(proxy.name, 'gate2a')

    @patch('ser2tcp.serial_proxy._server.Server')
    def test_name_default_empty(self, _mock_server):
        proxy = SerialProxy(
            {'serial': {'port': '/dev/ttyUSB0'},
             'servers': [{'protocol': 'tcp', 'address': '0.0.0.0',
                 'port': 10001}]})
        self.assertEqual(proxy.name, '')

    @patch('ser2tcp.serial_proxy._server.Server')
    def test_name_used_in_log(self, _mock_server):
        from unittest.mock import Mock
        log = Mock()
        proxy = SerialProxy(
            {'name': 'mydev', 'serial': {'port': '/dev/ttyUSB0'},
             'servers': [{'protocol': 'tcp', 'address': '0.0.0.0',
                 'port': 10001}]},
            log=log)
        log.info.assert_any_call("Serial: %s", 'mydev')


class TestSerialReaderThread(unittest.TestCase):
    """Test reader thread for platforms without fileno() support"""

    def _make_proxy(self):
        proxy = SerialProxy.__new__(SerialProxy)
        _mock_init(proxy)
        proxy._log = MagicMock()
        proxy._serial_config = {'port': '/dev/ttyUSB0'}
        return proxy

    def test_fileno_supported_no_thread(self):
        """No reader thread when fileno() works"""
        proxy = self._make_proxy()
        proxy._serial = MagicMock()
        proxy._serial.fileno.return_value = 3
        proxy._start_reader_thread_if_needed()
        self.assertIsNone(proxy._reader_thread)

    def test_fileno_not_supported_starts_thread(self):
        """Reader thread started when fileno() raises OSError"""
        proxy = self._make_proxy()
        proxy._serial = MagicMock()
        proxy._serial.in_waiting = 0
        proxy._serial.fileno.side_effect = OSError("fileno")
        proxy._serial.read.side_effect = OSError("closed")
        proxy._start_reader_thread_if_needed()
        self.assertIsNotNone(proxy._reader_thread)
        proxy._stop_reader_thread()

    def test_start_stop_reader_thread(self):
        """Reader thread starts and stops cleanly"""
        proxy = self._make_proxy()
        proxy._serial = MagicMock()
        proxy._serial.in_waiting = 0
        proxy._serial.read.side_effect = OSError("closed")
        proxy._start_reader_thread()
        self.assertIsNotNone(proxy._reader_thread)
        self.assertIsNotNone(proxy._reader_sock_r)
        self.assertIsNotNone(proxy._reader_sock_w)
        self.assertTrue(proxy._reader_running)
        proxy._stop_reader_thread()
        self.assertIsNone(proxy._reader_thread)
        self.assertIsNone(proxy._reader_sock_r)
        self.assertIsNone(proxy._reader_sock_w)
        self.assertFalse(proxy._reader_running)

    def test_reader_thread_forwards_data(self):
        """Reader thread forwards serial data through socketpair"""
        proxy = self._make_proxy()
        proxy._serial = MagicMock()
        proxy._serial.in_waiting = 5
        proxy._serial.read.side_effect = [b'hello', OSError("closed")]
        proxy._start_reader_thread()
        proxy._reader_thread.join(timeout=2)
        data = proxy._reader_sock_r.recv(4096)
        self.assertEqual(data, b'hello')
        proxy._stop_reader_thread()

    def test_read_sockets_uses_socketpair(self):
        """read_sockets() returns socketpair when reader thread is active"""
        proxy = self._make_proxy()
        proxy._serial = MagicMock()
        proxy._serial.in_waiting = 0
        proxy._serial.read.side_effect = OSError("closed")
        proxy._start_reader_thread()
        sockets = proxy.read_sockets()
        self.assertIn(proxy._reader_sock_r, sockets)
        self.assertNotIn(proxy._serial, sockets)
        proxy._stop_reader_thread()

    def test_read_sockets_uses_serial_directly(self):
        """read_sockets() returns serial when no reader thread"""
        proxy = self._make_proxy()
        proxy._serial = MagicMock()
        sockets = proxy.read_sockets()
        self.assertIn(proxy._serial, sockets)


if __name__ == "__main__":
    unittest.main()
