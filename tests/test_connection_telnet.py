"""Tests for ConnectionTelnet class"""

import unittest
from unittest.mock import Mock

from ser2tcp.connection_telnet import ConnectionTelnet


class MockSocket:
    """Mock socket for testing"""
    def __init__(self):
        self.sent_data = bytearray()
        self.closed = False
        self._fileno = 5

    def send(self, data):
        self.sent_data.extend(data)
        return len(data)

    def close(self):
        self.closed = True

    def fileno(self):
        return self._fileno


class TestConnectionTelnet(unittest.TestCase):
    def _make_connection(self):
        """Helper to create ConnectionTelnet with mock socket"""
        mock_socket = MockSocket()
        addr = ('127.0.0.1', 12345)
        mock_serial = Mock()
        log = Mock()
        conn = ConnectionTelnet(
            (mock_socket, addr),
            mock_serial,
            log=log)
        # Flush initial negotiation
        conn.flush()
        mock_socket.sent_data.clear()
        return conn, mock_serial

    def test_send_escapes_iac(self):
        """IAC bytes (0xff) should be escaped to 0xff 0xff"""
        conn, _ = self._make_connection()
        conn.send(b'\xff')
        conn.flush()
        self.assertEqual(conn.socket().sent_data, b'\xff\xff')

    def test_send_escapes_multiple_iac(self):
        conn, _ = self._make_connection()
        conn.send(b'a\xff b\xff c')
        conn.flush()
        self.assertEqual(conn.socket().sent_data, b'a\xff\xff b\xff\xff c')

    def test_on_received_plain_data(self):
        """Plain data should be forwarded to serial"""
        conn, serial = self._make_connection()
        conn.on_received(b'hello')
        serial.send.assert_called_once_with(bytearray(b'hello'))

    def test_on_received_escaped_iac(self):
        """Escaped IAC (0xff 0xff) should become single 0xff"""
        conn, serial = self._make_connection()
        conn.on_received(b'\xff\xff')
        serial.send.assert_called_once_with(bytes((0xff,)))

    def test_on_received_telnet_will_command(self):
        """TELNET WILL command should not be forwarded"""
        conn, serial = self._make_connection()
        # IAC WILL 0x01 (echo)
        conn.on_received(bytes((0xff, 0xfb, 0x01)))
        serial.send.assert_not_called()

    def test_on_received_telnet_wont_command(self):
        """TELNET WONT command should not be forwarded"""
        conn, serial = self._make_connection()
        # IAC WONT 0x01
        conn.on_received(bytes((0xff, 0xfc, 0x01)))
        serial.send.assert_not_called()

    def test_on_received_telnet_do_command(self):
        """TELNET DO command should not be forwarded"""
        conn, serial = self._make_connection()
        # IAC DO 0x01
        conn.on_received(bytes((0xff, 0xfd, 0x01)))
        serial.send.assert_not_called()

    def test_on_received_telnet_dont_command(self):
        """TELNET DONT command should not be forwarded"""
        conn, serial = self._make_connection()
        # IAC DONT 0x01
        conn.on_received(bytes((0xff, 0xfe, 0x01)))
        serial.send.assert_not_called()

    def test_on_received_mixed_data_and_command(self):
        """Data mixed with TELNET commands"""
        conn, serial = self._make_connection()
        # "hello" + IAC WILL 0x01 + "world"
        conn.on_received(b'hello\xff\xfb\x01world')
        # Should receive "hello" then "world"
        calls = serial.send.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][0][0], bytearray(b'hello'))
        self.assertEqual(calls[1][0][0], bytearray(b'world'))

    def test_on_received_subnegotiation(self):
        """TELNET subnegotiation should be handled"""
        conn, serial = self._make_connection()
        # IAC SB 0x22 (some data) IAC SE
        conn.on_received(bytes((0xff, 0xfa, 0x22, 0x01, 0x02, 0xff, 0xf0)))
        serial.send.assert_not_called()

    def test_initial_negotiation_sent(self):
        """Initial TELNET negotiation should be sent on connect"""
        mock_socket = MockSocket()
        addr = ('127.0.0.1', 12345)
        mock_serial = Mock()
        log = Mock()
        conn = ConnectionTelnet((mock_socket, addr), mock_serial, log=log)
        conn.flush()
        # Should contain IAC DO 0x22 and IAC WILL 0x01
        self.assertIn(bytes((0xff, 0xfd, 0x22)), mock_socket.sent_data)
        self.assertIn(bytes((0xff, 0xfb, 0x01)), mock_socket.sent_data)


class TestTelnetConstants(unittest.TestCase):
    def test_iac_value(self):
        self.assertEqual(ConnectionTelnet.TELNET_IAC, 0xff)

    def test_command_values(self):
        self.assertEqual(ConnectionTelnet.TELNET_WILL, 0xfb)
        self.assertEqual(ConnectionTelnet.TELNET_WONT, 0xfc)
        self.assertEqual(ConnectionTelnet.TELNET_DO, 0xfd)
        self.assertEqual(ConnectionTelnet.TELNET_DONT, 0xfe)

    def test_subnegotiation_values(self):
        self.assertEqual(ConnectionTelnet.TELNET_SB, 0xfa)
        self.assertEqual(ConnectionTelnet.TELNET_SE, 0xf0)


if __name__ == "__main__":
    unittest.main()
