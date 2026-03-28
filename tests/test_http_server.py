"""Tests for HTTP server wrapper"""

import unittest
from unittest.mock import Mock, MagicMock, patch

from ser2tcp.http_auth import hash_password
from ser2tcp.http_server import HttpServerWrapper


class MockClient:
    """Mock uhttp HttpConnection"""
    def __init__(self, method='GET', path='/', headers=None, query=None,
            data=None):
        self.method = method
        self.path = path
        self.headers = headers or {}
        self.query = query
        self.data = data
        self.responded = None
        self.respond_status = None

    def respond(self, data=None, status=200, headers=None, cookies=None):
        self.responded = data
        self.respond_status = status

    def respond_file(self, file_name, headers=None):
        self.responded = ('file', file_name)
        self.respond_status = 200


def make_wrapper(auth_config=None, serial_proxies=None):
    """Create HttpServerWrapper with mocked uhttp server"""
    http_config = {'address': '127.0.0.1', 'port': 0}
    # Auth config goes at root level of configuration
    configuration = {'http': [http_config]}
    if auth_config:
        if 'users' in auth_config:
            configuration['users'] = auth_config['users']
        if 'tokens' in auth_config:
            configuration['tokens'] = auth_config['tokens']
        if 'session_timeout' in auth_config:
            configuration['session_timeout'] = auth_config['session_timeout']
    proxies = serial_proxies if serial_proxies is not None else []
    with patch('ser2tcp.http_server._uhttp_server.HttpServer'):
        return HttpServerWrapper(http_config, proxies, log=Mock(),
            configuration=configuration)


class TestRouting(unittest.TestCase):
    def test_api_status_no_auth(self):
        wrapper = make_wrapper()
        client = MockClient(path='/api/status')
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 200)
        self.assertIn('ports', client.responded)

    def test_api_ports_no_auth(self):
        wrapper = make_wrapper()
        client = MockClient(path='/api/ports')
        with patch('ser2tcp.http_server._list_ports.comports', return_value=[]):
            wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 200)

    def test_api_unknown_returns_404(self):
        wrapper = make_wrapper()
        client = MockClient(path='/api/unknown')
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 404)

    def test_static_index(self):
        wrapper = make_wrapper()
        client = MockClient(path='/')
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 200)
        self.assertEqual(client.responded[0], 'file')
        self.assertTrue(client.responded[1].endswith('index.html'))

    def test_static_not_found(self):
        wrapper = make_wrapper()
        client = MockClient(path='/nonexistent.html')
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 404)

    def test_static_path_traversal(self):
        wrapper = make_wrapper()
        client = MockClient(path='/../../../etc/passwd')
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 404)

    def test_post_unknown_returns_404(self):
        wrapper = make_wrapper()
        client = MockClient(method='POST', path='/api/unknown')
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 404)


class TestAuth(unittest.TestCase):
    def _auth_config(self):
        return {
            'users': [{
                'login': 'admin',
                'password': hash_password('secret'),
                'admin': True,
            }],
            'tokens': [
                {'token': 'api-key', 'name': 'bot'},
            ],
        }

    def test_api_requires_auth(self):
        wrapper = make_wrapper(auth_config=self._auth_config())
        client = MockClient(path='/api/status')
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 401)

    def test_api_with_bearer(self):
        wrapper = make_wrapper(auth_config=self._auth_config())
        # Login first
        login_client = MockClient(
            method='POST', path='/api/login',
            data={'login': 'admin', 'password': 'secret'})
        wrapper._handle_request(login_client)
        self.assertEqual(login_client.respond_status, 200)
        token = login_client.responded['token']
        # Use token
        client = MockClient(
            path='/api/status',
            headers={'authorization': f'Bearer {token}'})
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 200)

    def test_api_with_query_token(self):
        wrapper = make_wrapper(auth_config=self._auth_config())
        login_client = MockClient(
            method='POST', path='/api/login',
            data={'login': 'admin', 'password': 'secret'})
        wrapper._handle_request(login_client)
        token = login_client.responded['token']
        client = MockClient(path='/api/status', query={'token': token})
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 200)

    def test_api_with_api_token(self):
        wrapper = make_wrapper(auth_config=self._auth_config())
        client = MockClient(
            path='/api/status',
            headers={'authorization': 'Bearer api-key'})
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 200)

    def test_invalid_token_401(self):
        wrapper = make_wrapper(auth_config=self._auth_config())
        client = MockClient(
            path='/api/status',
            headers={'authorization': 'Bearer invalid'})
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 401)

    def test_login_wrong_password(self):
        wrapper = make_wrapper(auth_config=self._auth_config())
        client = MockClient(
            method='POST', path='/api/login',
            data={'login': 'admin', 'password': 'wrong'})
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 401)

    def test_login_unknown_user(self):
        wrapper = make_wrapper(auth_config=self._auth_config())
        client = MockClient(
            method='POST', path='/api/login',
            data={'login': 'nobody', 'password': 'x'})
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 401)

    def test_login_invalid_data(self):
        wrapper = make_wrapper(auth_config=self._auth_config())
        client = MockClient(
            method='POST', path='/api/login', data='not json')
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 400)

    def test_login_no_auth_configured(self):
        wrapper = make_wrapper()
        client = MockClient(
            method='POST', path='/api/login',
            data={'login': 'admin', 'password': 'x'})
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 404)

    def test_logout(self):
        wrapper = make_wrapper(auth_config=self._auth_config())
        login_client = MockClient(
            method='POST', path='/api/login',
            data={'login': 'admin', 'password': 'secret'})
        wrapper._handle_request(login_client)
        token = login_client.responded['token']
        # Logout
        logout_client = MockClient(
            method='POST', path='/api/logout',
            headers={'authorization': f'Bearer {token}'})
        wrapper._handle_request(logout_client)
        self.assertEqual(logout_client.respond_status, 200)
        # Token no longer valid
        client = MockClient(
            path='/api/status',
            headers={'authorization': f'Bearer {token}'})
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 401)

    def test_static_no_auth_needed(self):
        wrapper = make_wrapper(auth_config=self._auth_config())
        client = MockClient(path='/')
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 200)


class TestApiStatus(unittest.TestCase):
    def _make_proxy(self, port=None, baudrate=None, match=None,
            connected=False, servers=None):
        proxy = Mock()
        cfg = {}
        if port:
            cfg['port'] = port
        if baudrate:
            cfg['baudrate'] = baudrate
        proxy.serial_config = cfg
        proxy.match = match
        proxy.is_connected = connected
        proxy.servers = servers or []
        return proxy

    def _make_server(self, protocol='TCP', address='0.0.0.0', port=21000,
            connections=None):
        server = Mock()
        server.protocol = protocol
        server.config = {'address': address, 'port': port}
        server.connections = connections or []
        return server

    def test_empty_proxies(self):
        wrapper = make_wrapper(serial_proxies=[])
        client = MockClient(path='/api/status')
        wrapper._handle_request(client)
        self.assertEqual(client.responded, {'ports': []})

    def test_proxy_with_port(self):
        proxy = self._make_proxy(port='/dev/ttyUSB0', baudrate=115200)
        wrapper = make_wrapper(serial_proxies=[proxy])
        client = MockClient(path='/api/status')
        wrapper._handle_request(client)
        serial = client.responded['ports'][0]['serial']
        self.assertEqual(serial['port'], '/dev/ttyUSB0')
        self.assertEqual(serial['baudrate'], 115200)

    def test_proxy_with_match(self):
        proxy = self._make_proxy(
            match={'serial_number': 'abc'}, connected=False)
        wrapper = make_wrapper(serial_proxies=[proxy])
        client = MockClient(path='/api/status')
        wrapper._handle_request(client)
        serial = client.responded['ports'][0]['serial']
        self.assertEqual(serial['match'], {'serial_number': 'abc'})
        self.assertFalse(serial['connected'])

    def test_proxy_no_baudrate(self):
        proxy = self._make_proxy(port='/dev/ttyS0')
        wrapper = make_wrapper(serial_proxies=[proxy])
        client = MockClient(path='/api/status')
        wrapper._handle_request(client)
        serial = client.responded['ports'][0]['serial']
        self.assertNotIn('baudrate', serial)

    def test_server_with_connections(self):
        con = Mock()
        con.address_str.return_value = '192.168.1.5:54321'
        server = self._make_server(connections=[con])
        proxy = self._make_proxy(port='/dev/ttyUSB0', servers=[server])
        wrapper = make_wrapper(serial_proxies=[proxy])
        client = MockClient(path='/api/status')
        wrapper._handle_request(client)
        srv = client.responded['ports'][0]['servers'][0]
        self.assertEqual(srv['protocol'], 'TCP')
        self.assertEqual(srv['port'], 21000)
        self.assertEqual(len(srv['connections']), 1)
        self.assertEqual(srv['connections'][0]['address'], '192.168.1.5:54321')

    def test_socket_server_no_port(self):
        server = self._make_server(protocol='SOCKET', address='/tmp/s.sock')
        proxy = self._make_proxy(port='/dev/ttyS0', servers=[server])
        wrapper = make_wrapper(serial_proxies=[proxy])
        client = MockClient(path='/api/status')
        wrapper._handle_request(client)
        srv = client.responded['ports'][0]['servers'][0]
        self.assertNotIn('port', srv)
        self.assertEqual(srv['address'], '/tmp/s.sock')


class TestApiPorts(unittest.TestCase):
    def _make_port_info(self, device='/dev/ttyUSB0', vid=None, pid=None,
            serial_number=None, manufacturer=None, product=None,
            location=None, description=None, hwid=None):
        p = Mock()
        p.device = device
        p.vid = vid
        p.pid = pid
        p.serial_number = serial_number
        p.manufacturer = manufacturer
        p.product = product
        p.location = location
        p.description = description
        p.hwid = hwid
        return p

    def test_empty(self):
        wrapper = make_wrapper()
        client = MockClient(path='/api/ports')
        with patch('ser2tcp.http_server._list_ports.comports',
                return_value=[]):
            wrapper._handle_request(client)
        self.assertEqual(client.responded, [])

    def test_usb_device(self):
        port = self._make_port_info(
            vid=0x303A, pid=0x4001,
            serial_number='abc', manufacturer='Espressif',
            product='ESP32', location='1-1')
        wrapper = make_wrapper()
        client = MockClient(path='/api/ports')
        with patch('ser2tcp.http_server._list_ports.comports',
                return_value=[port]):
            wrapper._handle_request(client)
        info = client.responded[0]
        self.assertEqual(info['device'], '/dev/ttyUSB0')
        self.assertEqual(info['vid'], '0x303A')
        self.assertEqual(info['pid'], '0x4001')
        self.assertEqual(info['serial_number'], 'abc')
        self.assertEqual(info['manufacturer'], 'Espressif')

    def test_non_usb_device(self):
        port = self._make_port_info(
            device='/dev/ttyS0', description='n/a', hwid='n/a')
        wrapper = make_wrapper()
        client = MockClient(path='/api/ports')
        with patch('ser2tcp.http_server._list_ports.comports',
                return_value=[port]):
            wrapper._handle_request(client)
        info = client.responded[0]
        self.assertEqual(info['device'], '/dev/ttyS0')
        self.assertNotIn('vid', info)
        self.assertNotIn('description', info)
        self.assertNotIn('hwid', info)

    def test_description_shown_when_not_na(self):
        port = self._make_port_info(description='USB Serial Port')
        wrapper = make_wrapper()
        client = MockClient(path='/api/ports')
        with patch('ser2tcp.http_server._list_ports.comports',
                return_value=[port]):
            wrapper._handle_request(client)
        self.assertEqual(client.responded[0]['description'], 'USB Serial Port')


class TestApiUsers(unittest.TestCase):
    def _auth_config(self):
        return {
            'users': [{
                'login': 'admin',
                'password': hash_password('secret'),
                'admin': True,
            }],
        }

    def _admin_token(self, wrapper):
        client = MockClient(
            method='POST', path='/api/login',
            data={'login': 'admin', 'password': 'secret'})
        wrapper._handle_request(client)
        return client.responded['token']

    def _auth_client(self, token, method='GET', path='/', data=None):
        return MockClient(
            method=method, path=path, data=data,
            headers={'authorization': f'Bearer {token}'})

    def test_list_users(self):
        wrapper = make_wrapper(auth_config=self._auth_config())
        token = self._admin_token(wrapper)
        client = self._auth_client(token, path='/api/users')
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 200)
        self.assertEqual(len(client.responded), 1)
        self.assertEqual(client.responded[0]['login'], 'admin')
        self.assertNotIn('password', client.responded[0])

    def test_add_user(self):
        wrapper = make_wrapper(auth_config=self._auth_config())
        token = self._admin_token(wrapper)
        client = self._auth_client(
            token, method='POST', path='/api/users',
            data={'login': 'new', 'password': 'pass123'})
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 201)
        # Verify new user can login
        login = MockClient(
            method='POST', path='/api/login',
            data={'login': 'new', 'password': 'pass123'})
        wrapper._handle_request(login)
        self.assertEqual(login.respond_status, 200)

    def test_add_user_with_hash(self):
        wrapper = make_wrapper(auth_config=self._auth_config())
        token = self._admin_token(wrapper)
        h = hash_password('hashed')
        client = self._auth_client(
            token, method='POST', path='/api/users',
            data={'login': 'new', 'password': h})
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 201)
        login = MockClient(
            method='POST', path='/api/login',
            data={'login': 'new', 'password': 'hashed'})
        wrapper._handle_request(login)
        self.assertEqual(login.respond_status, 200)

    def test_add_user_duplicate(self):
        wrapper = make_wrapper(auth_config=self._auth_config())
        token = self._admin_token(wrapper)
        client = self._auth_client(
            token, method='POST', path='/api/users',
            data={'login': 'admin', 'password': 'x'})
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 400)

    def test_add_user_missing_fields(self):
        wrapper = make_wrapper(auth_config=self._auth_config())
        token = self._admin_token(wrapper)
        client = self._auth_client(
            token, method='POST', path='/api/users',
            data={'login': 'new'})
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 400)

    def test_add_user_non_admin(self):
        auth = self._auth_config()
        auth['users'].append({
            'login': 'viewer', 'password': hash_password('pass'),
        })
        wrapper = make_wrapper(auth_config=auth)
        login = MockClient(
            method='POST', path='/api/login',
            data={'login': 'viewer', 'password': 'pass'})
        wrapper._handle_request(login)
        token = login.responded['token']
        client = self._auth_client(
            token, method='POST', path='/api/users',
            data={'login': 'x', 'password': 'x'})
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 403)

    def test_update_user_password(self):
        wrapper = make_wrapper(auth_config=self._auth_config())
        token = self._admin_token(wrapper)
        client = self._auth_client(
            token, method='PUT', path='/api/users/admin',
            data={'password': 'newpass'})
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 200)
        login = MockClient(
            method='POST', path='/api/login',
            data={'login': 'admin', 'password': 'newpass'})
        wrapper._handle_request(login)
        self.assertEqual(login.respond_status, 200)

    def test_update_user_not_found(self):
        wrapper = make_wrapper(auth_config=self._auth_config())
        token = self._admin_token(wrapper)
        client = self._auth_client(
            token, method='PUT', path='/api/users/nobody',
            data={'password': 'x'})
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 404)

    def test_delete_user(self):
        auth = self._auth_config()
        auth['users'].append({
            'login': 'toremove', 'password': hash_password('x'),
        })
        wrapper = make_wrapper(auth_config=auth)
        token = self._admin_token(wrapper)
        client = self._auth_client(
            token, method='DELETE', path='/api/users/toremove')
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 200)
        login = MockClient(
            method='POST', path='/api/login',
            data={'login': 'toremove', 'password': 'x'})
        wrapper._handle_request(login)
        self.assertEqual(login.respond_status, 401)

    def test_delete_user_not_found(self):
        wrapper = make_wrapper(auth_config=self._auth_config())
        token = self._admin_token(wrapper)
        client = self._auth_client(
            token, method='DELETE', path='/api/users/nobody')
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 404)

    def test_users_list_no_auth(self):
        wrapper = make_wrapper()
        client = MockClient(path='/api/users')
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 200)
        self.assertEqual(client.responded, [])

    def test_bootstrap_add_first_user(self):
        """Add first user without any auth configured"""
        wrapper = make_wrapper()
        client = MockClient(
            method='POST', path='/api/users',
            data={'login': 'admin', 'password': 'secret', 'admin': True})
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 201)
        # Auth is now active - need token
        client2 = MockClient(path='/api/status')
        wrapper._handle_request(client2)
        self.assertEqual(client2.respond_status, 401)
        # Can login with new user
        login = MockClient(
            method='POST', path='/api/login',
            data={'login': 'admin', 'password': 'secret'})
        wrapper._handle_request(login)
        self.assertEqual(login.respond_status, 200)

    def test_bootstrap_empty_auth(self):
        """Add first user when auth section exists but empty"""
        wrapper = make_wrapper(auth_config={})
        client = MockClient(
            method='POST', path='/api/users',
            data={'login': 'admin', 'password': 'pass', 'admin': True})
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 201)


class TestConfigVariants(unittest.TestCase):
    def test_single_dict_config(self):
        with patch('ser2tcp.http_server._uhttp_server.HttpServer') as mock:
            HttpServerWrapper(
                {'address': '0.0.0.0', 'port': 8080}, [], log=Mock())
            mock.assert_called_once()

    def test_list_config(self):
        with patch('ser2tcp.http_server._uhttp_server.HttpServer') as mock:
            HttpServerWrapper([
                {'address': '0.0.0.0', 'port': 8080},
                {'address': '0.0.0.0', 'port': 8081},
            ], [], log=Mock())
            self.assertEqual(mock.call_count, 2)
