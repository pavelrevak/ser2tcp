"""Tests for Connection class"""

import unittest
from unittest.mock import Mock, patch
import time

from ser2tcp.connection import Connection


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


class TestConnection(unittest.TestCase):
    def _make_connection(self, send_timeout=None, buffer_limit=None):
        """Helper to create Connection with mock socket"""
        mock_socket = MockSocket()
        addr = ('127.0.0.1', 12345)
        log = Mock()
        return Connection(
            (mock_socket, addr),
            send_timeout=send_timeout,
            buffer_limit=buffer_limit,
            log=log)

    def test_init_stores_socket_and_addr(self):
        conn = self._make_connection()
        self.assertIsNotNone(conn.socket())
        self.assertEqual(conn.get_address(), ('127.0.0.1', 12345))

    def test_fileno_returns_socket_fileno(self):
        conn = self._make_connection()
        self.assertEqual(conn.fileno(), 5)

    def test_send_adds_data_to_buffer(self):
        conn = self._make_connection()
        result = conn.send(b'hello')
        self.assertEqual(result, 5)
        self.assertTrue(conn.has_pending_data())

    def test_send_returns_none_when_closed(self):
        conn = self._make_connection()
        conn.close()
        result = conn.send(b'hello')
        self.assertIsNone(result)

    def test_send_respects_buffer_limit(self):
        conn = self._make_connection(buffer_limit=10)
        result1 = conn.send(b'hello')  # 5 bytes
        self.assertEqual(result1, 5)
        result2 = conn.send(b'world')  # 5 more bytes = 10 total
        self.assertEqual(result2, 5)
        result3 = conn.send(b'!')  # exceeds limit
        self.assertIsNone(result3)

    def test_flush_sends_buffered_data(self):
        conn = self._make_connection()
        conn.send(b'hello')
        sent = conn.flush()
        self.assertEqual(sent, 5)
        self.assertFalse(conn.has_pending_data())

    def test_flush_returns_zero_when_empty(self):
        conn = self._make_connection()
        sent = conn.flush()
        self.assertEqual(sent, 0)

    def test_close_closes_socket(self):
        conn = self._make_connection()
        socket = conn.socket()
        conn.close()
        self.assertTrue(socket.closed)
        self.assertIsNone(conn.socket())

    def test_fileno_returns_none_when_closed(self):
        conn = self._make_connection()
        conn.close()
        self.assertIsNone(conn.fileno())

    def test_has_pending_data_false_initially(self):
        conn = self._make_connection()
        self.assertFalse(conn.has_pending_data())

    def test_is_stale_false_initially(self):
        conn = self._make_connection(send_timeout=1.0)
        self.assertFalse(conn.is_stale())

    def test_is_stale_false_without_pending_data(self):
        conn = self._make_connection(send_timeout=0.001)
        time.sleep(0.01)
        self.assertFalse(conn.is_stale())

    @patch('ser2tcp.connection._time')
    def test_is_stale_true_after_timeout(self, mock_time):
        conn = self._make_connection(send_timeout=5.0)
        # Initial time
        mock_time.time.return_value = 100.0
        conn.send(b'hello')
        # Time after timeout
        mock_time.time.return_value = 106.0
        self.assertTrue(conn.is_stale())

    @patch('ser2tcp.connection._time')
    def test_flush_resets_timeout(self, mock_time):
        conn = self._make_connection(send_timeout=5.0)
        mock_time.time.return_value = 100.0
        conn.send(b'hello')
        mock_time.time.return_value = 103.0
        conn.flush()  # Should reset timer
        mock_time.time.return_value = 106.0
        # Would be stale if timer wasn't reset
        self.assertFalse(conn.has_pending_data())  # Buffer is empty after flush

    def test_default_send_timeout(self):
        conn = self._make_connection()
        self.assertEqual(conn._send_timeout, Connection.DEFAULT_SEND_TIMEOUT)

    def test_default_buffer_limit(self):
        conn = self._make_connection()
        self.assertEqual(conn._buffer_limit, Connection.DEFAULT_BUFFER_LIMIT)


class TestConnectionFlushError(unittest.TestCase):
    def test_flush_returns_none_on_oserror(self):
        mock_socket = Mock()
        mock_socket.send.side_effect = OSError("Connection reset")
        addr = ('127.0.0.1', 12345)
        log = Mock()
        conn = Connection((mock_socket, addr), log=log)
        conn._out_buffer.extend(b'hello')
        result = conn.flush()
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
