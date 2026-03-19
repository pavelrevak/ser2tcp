"""Tests for ConnectionSsl class"""

import unittest
import unittest.mock
from unittest.mock import Mock

from ser2tcp.connection_ssl import ConnectionSsl


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


class TestConnectionSsl(unittest.TestCase):
    def _make_connection(self):
        """Helper to create ConnectionSsl with mock socket"""
        mock_socket = MockSocket()
        mock_ssl_socket = MockSocket()
        addr = ('127.0.0.1', 12345)
        mock_serial = Mock()
        log = Mock()
        mock_context = Mock()
        mock_context.wrap_socket.return_value = mock_ssl_socket
        conn = ConnectionSsl(
            (mock_socket, addr),
            mock_serial,
            log=log,
            ssl_context=mock_context)
        return conn, mock_serial, mock_context, mock_socket

    def test_wraps_socket_with_ssl_context(self):
        """SSL context should wrap the socket"""
        conn, _, context, raw_socket = self._make_connection()
        context.wrap_socket.assert_called_once_with(
            raw_socket, server_side=True)

    def test_log_connected_shows_ssl(self):
        """Log message should show SSL protocol"""
        mock_socket = MockSocket()
        mock_ssl_socket = MockSocket()
        addr = ('127.0.0.1', 12345)
        mock_serial = Mock()
        log = Mock()
        mock_context = Mock()
        mock_context.wrap_socket.return_value = mock_ssl_socket
        conn = ConnectionSsl(
            (mock_socket, addr),
            mock_serial,
            log=log,
            ssl_context=mock_context)
        # Check that SSL was logged (first call, before any disconnect)
        first_call = log.info.call_args_list[0]
        self.assertEqual(
            first_call,
            unittest.mock.call(
                "Client connected: %s SSL", '127.0.0.1:12345'))
        conn.close()

    def test_on_received_forwards_to_serial(self):
        """Data should be forwarded to serial"""
        conn, serial, _, _ = self._make_connection()
        conn.on_received(b'hello')
        serial.send.assert_called_once_with(b'hello')

    def test_send_adds_to_buffer(self):
        """Send should add data to buffer"""
        conn, _, _, _ = self._make_connection()
        result = conn.send(b'test')
        self.assertEqual(result, 4)
        self.assertTrue(conn.has_pending_data())


if __name__ == "__main__":
    unittest.main()
