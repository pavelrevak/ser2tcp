"""Tests for ServerMonitor"""

import unittest
from unittest.mock import MagicMock, patch

import ser2tcp.server_monitor as monitor


class MockSerialProxy:
    """Mock SerialProxy for testing"""

    def __init__(self, name='test-port'):
        self._name = name
        self._monitors = []

    @property
    def name(self):
        return self._name

    def add_monitor(self, callback):
        self._monitors.append(callback)

    def remove_monitor(self, callback):
        if callback in self._monitors:
            self._monitors.remove(callback)

    def notify(self, direction, data):
        for cb in list(self._monitors):
            cb(direction, data)


class MockClient:
    """Mock uhttp client for testing"""

    def __init__(self):
        self.is_websocket = True
        self.socket = MagicMock()
        self.addr = ('127.0.0.1', 12345)
        self.sent = []
        self.closed = False
        self.close_code = None
        self.close_reason = None

    def ws_send(self, data):
        if self.closed:
            raise OSError("Connection closed")
        self.sent.append(data)

    def ws_close(self, code, reason):
        self.closed = True
        self.close_code = code
        self.close_reason = reason


class TestServerMonitor(unittest.TestCase):
    """Test ServerMonitor initialization"""

    def test_init(self):
        proxy = MockSerialProxy()
        srv = monitor.ServerMonitor(proxy)
        self.assertEqual(srv.connections, [])

    def test_dir_constants(self):
        self.assertEqual(monitor.ServerMonitor.DIR_TX, 1)
        self.assertEqual(monitor.ServerMonitor.DIR_RX, 2)


class TestConnections(unittest.TestCase):
    """Test connection management"""

    def setUp(self):
        self.proxy = MockSerialProxy('myport')
        self.srv = monitor.ServerMonitor(self.proxy)

    def test_add_connection(self):
        client = MockClient()
        self.srv.add_connection(client)
        self.assertIn(client, self.srv.connections)

    def test_add_connection_registers_monitor(self):
        client = MockClient()
        self.srv.add_connection(client)
        self.assertEqual(len(self.proxy._monitors), 1)

    def test_remove_connection(self):
        client = MockClient()
        self.srv.add_connection(client)
        self.srv.remove_connection(client)
        self.assertNotIn(client, self.srv.connections)

    def test_remove_connection_unregisters_monitor(self):
        client = MockClient()
        self.srv.add_connection(client)
        self.srv.remove_connection(client)
        self.assertEqual(len(self.proxy._monitors), 0)

    def test_multiple_clients_share_monitor(self):
        client1 = MockClient()
        client2 = MockClient()
        self.srv.add_connection(client1)
        self.srv.add_connection(client2)
        # Only one monitor callback
        self.assertEqual(len(self.proxy._monitors), 1)
        # Remove first, monitor still registered
        self.srv.remove_connection(client1)
        self.assertEqual(len(self.proxy._monitors), 1)
        # Remove last, monitor unregistered
        self.srv.remove_connection(client2)
        self.assertEqual(len(self.proxy._monitors), 0)


class TestDataForwarding(unittest.TestCase):
    """Test data forwarding to clients"""

    def setUp(self):
        self.proxy = MockSerialProxy('myport')
        self.srv = monitor.ServerMonitor(self.proxy)

    def test_tx_data_prefixed(self):
        client = MockClient()
        self.srv.add_connection(client)
        self.proxy.notify(1, b'hello')
        self.assertEqual(len(client.sent), 1)
        self.assertEqual(client.sent[0], b'\x01hello')

    def test_rx_data_prefixed(self):
        client = MockClient()
        self.srv.add_connection(client)
        self.proxy.notify(2, b'world')
        self.assertEqual(len(client.sent), 1)
        self.assertEqual(client.sent[0], b'\x02world')

    def test_broadcast_to_all_clients(self):
        client1 = MockClient()
        client2 = MockClient()
        self.srv.add_connection(client1)
        self.srv.add_connection(client2)
        self.proxy.notify(1, b'test')
        self.assertEqual(client1.sent, [b'\x01test'])
        self.assertEqual(client2.sent, [b'\x01test'])

    def test_failed_send_removes_client(self):
        client = MockClient()
        self.srv.add_connection(client)
        client.closed = True  # Simulate disconnect
        self.proxy.notify(1, b'test')
        self.assertNotIn(client, self.srv.connections)


class TestProcessStale(unittest.TestCase):
    """Test stale connection cleanup"""

    def setUp(self):
        self.proxy = MockSerialProxy()
        self.srv = monitor.ServerMonitor(self.proxy)

    def test_removes_non_websocket(self):
        client = MockClient()
        self.srv.add_connection(client)
        client.is_websocket = False
        self.srv.process_stale()
        self.assertNotIn(client, self.srv.connections)

    def test_removes_closed_socket(self):
        client = MockClient()
        self.srv.add_connection(client)
        client.socket = None
        self.srv.process_stale()
        self.assertNotIn(client, self.srv.connections)

    def test_keeps_active(self):
        client = MockClient()
        self.srv.add_connection(client)
        self.srv.process_stale()
        self.assertIn(client, self.srv.connections)


class TestClose(unittest.TestCase):
    """Test server close"""

    def test_close_all_connections(self):
        proxy = MockSerialProxy()
        srv = monitor.ServerMonitor(proxy)
        client1 = MockClient()
        client2 = MockClient()
        srv.add_connection(client1)
        srv.add_connection(client2)
        srv.close()
        self.assertEqual(srv.connections, [])
        self.assertTrue(client1.closed)
        self.assertTrue(client2.closed)
        self.assertEqual(client1.close_code, 1001)

    def test_close_unregisters_monitor(self):
        proxy = MockSerialProxy()
        srv = monitor.ServerMonitor(proxy)
        client = MockClient()
        srv.add_connection(client)
        srv.close()
        self.assertEqual(len(proxy._monitors), 0)


if __name__ == '__main__':
    unittest.main()
