"""Tests for WebSocket virtual server"""

import json
import unittest
from unittest.mock import Mock, MagicMock, patch, call

from ser2tcp.server import ConfigError
from ser2tcp.server_websocket import ServerWebSocket


def make_ws_server(endpoint='test', token=None, data=True, control=None):
    """Create ServerWebSocket with mock serial proxy"""
    config = {'protocol': 'websocket', 'endpoint': endpoint}
    if token:
        config['token'] = token
    if not data:
        config['data'] = False
    if control:
        config['control'] = control
    serial = Mock()
    serial.connect.return_value = True
    serial.get_signals.return_value = 0
    serial.disconnect = Mock()
    serial.send = Mock()
    serial.set_rts = Mock()
    serial.set_dtr = Mock()
    return ServerWebSocket(config, serial, log=Mock())


def make_ws_client(addr=('127.0.0.1', 12345)):
    """Create mock uhttp WebSocket client"""
    client = Mock()
    client.addr = addr
    client.is_websocket = True
    client.ws_send = Mock()
    client.ws_close = Mock()
    client.ws_message = None
    return client


class TestConfig(unittest.TestCase):
    def test_endpoint_required(self):
        with self.assertRaises(ConfigError):
            make_ws_server(endpoint=None)

    def test_data_false_requires_control(self):
        with self.assertRaises(ConfigError):
            make_ws_server(data=False, control=None)

    def test_data_false_with_control(self):
        srv = make_ws_server(
            data=False, control={'rts': True, 'signals': ['rts']})
        self.assertFalse(srv.data_enabled)

    def test_properties(self):
        srv = make_ws_server(endpoint='dev1', token='secret')
        self.assertEqual(srv.protocol, 'WEBSOCKET')
        self.assertEqual(srv.endpoint, 'dev1')
        self.assertEqual(srv.token, 'secret')
        self.assertTrue(srv.data_enabled)
        self.assertIsNone(srv.control)


class TestConnections(unittest.TestCase):
    def test_add_connection(self):
        srv = make_ws_server()
        client = make_ws_client()
        srv.add_connection(client)
        self.assertEqual(len(srv.connections), 1)
        self.assertTrue(srv.has_connections())
        srv._serial.connect.assert_called_once()

    def test_add_connection_serial_fail(self):
        srv = make_ws_server()
        srv._serial.connect.return_value = False
        client = make_ws_client()
        srv.add_connection(client)
        self.assertEqual(len(srv.connections), 0)
        client.ws_close.assert_called_once()

    def test_remove_connection(self):
        srv = make_ws_server()
        client = make_ws_client()
        srv.add_connection(client)
        srv.remove_connection(client)
        self.assertEqual(len(srv.connections), 0)
        srv._serial.disconnect.assert_called_once()

    def test_remove_unknown_connection(self):
        srv = make_ws_server()
        client = make_ws_client()
        srv.remove_connection(client)  # should not raise

    def test_close_connections(self):
        srv = make_ws_server()
        clients = [make_ws_client(('127.0.0.1', p)) for p in range(3)]
        for c in clients:
            srv.add_connection(c)
        srv.close_connections()
        self.assertEqual(len(srv.connections), 0)
        for c in clients:
            c.ws_close.assert_called_once()

    def test_process_stale_removes_closed(self):
        srv = make_ws_server()
        client = make_ws_client()
        srv.add_connection(client)
        client.is_websocket = False  # simulate closed
        srv.process_stale()
        self.assertEqual(len(srv.connections), 0)


class TestDataForwarding(unittest.TestCase):
    def test_send_binary_to_clients(self):
        srv = make_ws_server()
        c1 = make_ws_client(('127.0.0.1', 1))
        c2 = make_ws_client(('127.0.0.1', 2))
        srv.add_connection(c1)
        srv.add_connection(c2)
        srv.send(b'\x01\x02\x03')
        c1.ws_send.assert_called_with(b'\x01\x02\x03')
        c2.ws_send.assert_called_with(b'\x01\x02\x03')

    def test_send_skipped_when_data_disabled(self):
        srv = make_ws_server(
            data=False, control={'rts': True, 'signals': ['rts']})
        client = make_ws_client()
        srv.add_connection(client)
        client.ws_send.reset_mock()  # clear initial signal report
        srv.send(b'\x01\x02')
        client.ws_send.assert_not_called()

    def test_receive_binary_forwards_to_serial(self):
        srv = make_ws_server()
        client = make_ws_client()
        client.ws_message = b'\x01\x02\x03'
        srv.add_connection(client)
        srv.process_message(client)
        srv._serial.send.assert_called_with(b'\x01\x02\x03')

    def test_receive_binary_ignored_when_data_disabled(self):
        srv = make_ws_server(
            data=False, control={'rts': True, 'signals': ['rts']})
        client = make_ws_client()
        client.ws_message = b'\x01\x02'
        srv.add_connection(client)
        srv.process_message(client)
        srv._serial.send.assert_not_called()

    def test_send_removes_failed_connection(self):
        srv = make_ws_server()
        client = make_ws_client()
        client.ws_send.side_effect = OSError
        srv.add_connection(client)
        srv.send(b'\x01')
        self.assertEqual(len(srv.connections), 0)


class TestControl(unittest.TestCase):
    def test_rts_command(self):
        srv = make_ws_server(control={'rts': True, 'signals': ['rts']})
        client = make_ws_client()
        client.ws_message = json.dumps({'rts': True})
        srv.add_connection(client)
        srv.process_message(client)
        srv._serial.set_rts.assert_called_with(True)

    def test_dtr_command(self):
        srv = make_ws_server(control={'dtr': True, 'signals': ['dtr']})
        client = make_ws_client()
        client.ws_message = json.dumps({'dtr': False})
        srv.add_connection(client)
        srv.process_message(client)
        srv._serial.set_dtr.assert_called_with(False)

    def test_rts_ignored_when_not_enabled(self):
        srv = make_ws_server(control={'rts': False, 'signals': ['rts']})
        client = make_ws_client()
        client.ws_message = json.dumps({'rts': True})
        srv.add_connection(client)
        srv.process_message(client)
        srv._serial.set_rts.assert_not_called()

    def test_control_ignored_without_config(self):
        srv = make_ws_server()  # no control
        client = make_ws_client()
        client.ws_message = json.dumps({'rts': True})
        srv.add_connection(client)
        srv.process_message(client)
        srv._serial.set_rts.assert_not_called()

    def test_invalid_json_ignored(self):
        srv = make_ws_server(control={'rts': True, 'signals': ['rts']})
        client = make_ws_client()
        client.ws_message = 'not json{'
        srv.add_connection(client)
        srv.process_message(client)  # should not raise

    def test_signal_report_on_connect(self):
        srv = make_ws_server(
            control={'signals': ['rts', 'cts']})
        srv._serial.get_signals.return_value = 0b000101  # rts + cts
        client = make_ws_client()
        srv.add_connection(client)
        # Should have sent signal report
        client.ws_send.assert_called_once()
        msg = json.loads(client.ws_send.call_args[0][0])
        self.assertEqual(msg['signals']['rts'], True)
        self.assertEqual(msg['signals']['cts'], True)

    def test_signal_report_filters_configured(self):
        srv = make_ws_server(
            control={'signals': ['rts']})
        srv._serial.get_signals.return_value = 0b111111  # all signals
        client = make_ws_client()
        srv.add_connection(client)
        msg = json.loads(client.ws_send.call_args[0][0])
        self.assertIn('rts', msg['signals'])
        self.assertNotIn('dtr', msg['signals'])
        self.assertNotIn('cts', msg['signals'])

    def test_send_signal_report_to_all(self):
        srv = make_ws_server(
            control={'signals': ['rts', 'dtr']})
        c1 = make_ws_client(('127.0.0.1', 1))
        c2 = make_ws_client(('127.0.0.1', 2))
        srv.add_connection(c1)
        srv.add_connection(c2)
        # Reset initial signal report calls
        c1.ws_send.reset_mock()
        c2.ws_send.reset_mock()
        srv.send_signal_report(0b01)  # rts only
        msg1 = json.loads(c1.ws_send.call_args[0][0])
        msg2 = json.loads(c2.ws_send.call_args[0][0])
        self.assertTrue(msg1['signals']['rts'])
        self.assertFalse(msg1['signals']['dtr'])
        self.assertEqual(msg1, msg2)

    def test_send_signal_report_no_control(self):
        srv = make_ws_server()  # no control
        client = make_ws_client()
        srv.add_connection(client)
        srv.send_signal_report(0b01)  # should be no-op
        client.ws_send.assert_not_called()


class TestSocketInterface(unittest.TestCase):
    """Verify no-op socket methods for select loop compatibility"""

    def test_read_sockets_empty(self):
        srv = make_ws_server()
        self.assertEqual(srv.read_sockets(), [])

    def test_write_sockets_empty(self):
        srv = make_ws_server()
        self.assertEqual(srv.write_sockets(), [])

    def test_process_read_noop(self):
        srv = make_ws_server()
        srv.process_read([])  # should not raise

    def test_process_write_noop(self):
        srv = make_ws_server()
        srv.process_write([])  # should not raise
