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

    def test_api_detect_no_auth(self):
        wrapper = make_wrapper()
        client = MockClient(path='/api/detect')
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
            connected=False, servers=None, name='',
            bytesize=None, parity=None, stopbits=None):
        proxy = Mock()
        cfg = {}
        if port:
            cfg['port'] = port
        if baudrate:
            cfg['baudrate'] = baudrate
        if bytesize:
            cfg['bytesize'] = bytesize
        if parity:
            cfg['parity'] = parity
        if stopbits:
            cfg['stopbits'] = stopbits
        proxy.serial_config = cfg
        proxy.match = match
        proxy.name = name
        proxy.is_connected = connected
        proxy.servers = servers or []
        return proxy

    def _make_server(self, protocol='TCP', address='0.0.0.0', port=21000,
            connections=None, ssl=None):
        server = Mock()
        server.protocol = protocol
        config = {'address': address, 'port': port}
        if ssl:
            config['ssl'] = ssl
        server.config = config
        server.connections = connections or []
        return server

    def test_empty_proxies(self):
        wrapper = make_wrapper(serial_proxies=[])
        client = MockClient(path='/api/status')
        wrapper._handle_request(client)
        self.assertEqual(client.responded['ports'], [])
        self.assertIn('admin', client.responded)

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

    def test_proxy_with_name(self):
        proxy = self._make_proxy(port='/dev/ttyUSB0', name='gate2a')
        wrapper = make_wrapper(serial_proxies=[proxy])
        client = MockClient(path='/api/status')
        wrapper._handle_request(client)
        self.assertEqual(client.responded['ports'][0]['name'], 'gate2a')

    def test_proxy_without_name(self):
        proxy = self._make_proxy(port='/dev/ttyUSB0')
        wrapper = make_wrapper(serial_proxies=[proxy])
        client = MockClient(path='/api/status')
        wrapper._handle_request(client)
        self.assertNotIn('name', client.responded['ports'][0])

    def test_serial_params_in_status(self):
        proxy = self._make_proxy(
            port='/dev/ttyUSB0', baudrate=115200,
            bytesize='SEVENBITS', parity='EVEN', stopbits='TWO')
        wrapper = make_wrapper(serial_proxies=[proxy])
        client = MockClient(path='/api/status')
        wrapper._handle_request(client)
        serial = client.responded['ports'][0]['serial']
        self.assertEqual(serial['bytesize'], 'SEVENBITS')
        self.assertEqual(serial['parity'], 'EVEN')
        self.assertEqual(serial['stopbits'], 'TWO')

    def test_ssl_config_in_status(self):
        ssl_cfg = {'certfile': 'server.crt', 'keyfile': 'server.key'}
        server = self._make_server(
            protocol='SSL', port=10443, ssl=ssl_cfg)
        proxy = self._make_proxy(
            port='/dev/ttyUSB0', servers=[server])
        wrapper = make_wrapper(serial_proxies=[proxy])
        client = MockClient(path='/api/status')
        wrapper._handle_request(client)
        srv = client.responded['ports'][0]['servers'][0]
        self.assertEqual(srv['ssl'], ssl_cfg)

    def test_no_ssl_config_for_tcp(self):
        server = self._make_server(protocol='TCP')
        proxy = self._make_proxy(
            port='/dev/ttyUSB0', servers=[server])
        wrapper = make_wrapper(serial_proxies=[proxy])
        client = MockClient(path='/api/status')
        wrapper._handle_request(client)
        srv = client.responded['ports'][0]['servers'][0]
        self.assertNotIn('ssl', srv)


class TestApiDisconnect(unittest.TestCase):
    def _make_connection(self, address='192.168.1.5:54321'):
        con = Mock()
        con.address_str.return_value = address
        return con

    def _make_server_with_con(self):
        con = self._make_connection()
        server = Mock()
        server.protocol = 'TCP'
        server.config = {'address': '0.0.0.0', 'port': 21000}
        server.connections = [con]
        return server, con

    def _make_proxy_with_con(self):
        server, con = self._make_server_with_con()
        proxy = Mock()
        proxy.serial_config = {'port': '/dev/ttyUSB0'}
        proxy.match = None
        proxy.name = ''
        proxy.is_connected = True
        proxy.servers = [server]
        return proxy, server, con

    def test_disconnect_client(self):
        proxy, server, con = self._make_proxy_with_con()
        wrapper = make_wrapper(serial_proxies=[proxy])
        client = MockClient(
            method='DELETE',
            path='/api/ports/0/connections/0/0')
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 200)
        server._remove_connection.assert_called_once_with(con)

    def test_disconnect_port_not_found(self):
        wrapper = make_wrapper(serial_proxies=[])
        client = MockClient(
            method='DELETE',
            path='/api/ports/0/connections/0/0')
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 404)

    def test_disconnect_server_not_found(self):
        proxy, _, _ = self._make_proxy_with_con()
        wrapper = make_wrapper(serial_proxies=[proxy])
        client = MockClient(
            method='DELETE',
            path='/api/ports/0/connections/5/0')
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 404)

    def test_disconnect_connection_not_found(self):
        proxy, _, _ = self._make_proxy_with_con()
        wrapper = make_wrapper(serial_proxies=[proxy])
        client = MockClient(
            method='DELETE',
            path='/api/ports/0/connections/0/5')
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 404)

    def test_disconnect_invalid_index(self):
        wrapper = make_wrapper(serial_proxies=[])
        client = MockClient(
            method='DELETE',
            path='/api/ports/0/connections/abc/0')
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 400)


class TestApiDetect(unittest.TestCase):
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
        client = MockClient(path='/api/detect')
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
        client = MockClient(path='/api/detect')
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
        client = MockClient(path='/api/detect')
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
        client = MockClient(path='/api/detect')
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


class TestApiPortsCrud(unittest.TestCase):
    """Tests for port configuration CRUD API"""

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

    def _port_config(self, port='/dev/ttyUSB0', baudrate=115200,
            protocol='tcp', address='0.0.0.0', srv_port=10001):
        cfg = {
            'serial': {'port': port, 'baudrate': baudrate},
            'servers': [{'protocol': protocol, 'address': address,
                'port': srv_port}],
        }
        return cfg

    def _make_wrapper_with_ports(self, port_configs=None):
        auth = self._auth_config()
        configuration = {
            'http': [{'address': '127.0.0.1', 'port': 0}],
            'users': auth['users'],
            'ports': port_configs or [],
        }
        proxies = []
        if port_configs:
            for cfg in port_configs:
                proxy = Mock()
                proxy.serial_config = cfg['serial']
                proxy.match = cfg['serial'].get('match')
                proxy.is_connected = False
                proxy.servers = []
                proxy.close = Mock()
                proxies.append(proxy)
        manager = Mock()
        with patch('ser2tcp.http_server._uhttp_server.HttpServer'):
            wrapper = HttpServerWrapper(
                {'address': '127.0.0.1', 'port': 0}, proxies,
                log=Mock(), configuration=configuration,
                server_manager=manager)
        return wrapper, manager

    def test_add_port(self):
        wrapper, manager = self._make_wrapper_with_ports()
        token = self._admin_token(wrapper)
        cfg = self._port_config()
        with patch.object(wrapper, '_create_proxy') as mock_create:
            mock_create.return_value = Mock()
            client = self._auth_client(
                token, method='POST', path='/api/ports', data=cfg)
            wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 201)
        self.assertEqual(client.responded['index'], 0)
        manager.add_server.assert_called_once()

    def test_add_port_missing_serial(self):
        wrapper, _ = self._make_wrapper_with_ports()
        token = self._admin_token(wrapper)
        client = self._auth_client(
            token, method='POST', path='/api/ports',
            data={'servers': [{'protocol': 'tcp', 'port': 10001}]})
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 400)

    def test_add_port_missing_servers(self):
        wrapper, _ = self._make_wrapper_with_ports()
        token = self._admin_token(wrapper)
        client = self._auth_client(
            token, method='POST', path='/api/ports',
            data={'serial': {'port': '/dev/ttyUSB0'}})
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 400)

    def test_add_port_empty_servers(self):
        wrapper, _ = self._make_wrapper_with_ports()
        token = self._admin_token(wrapper)
        client = self._auth_client(
            token, method='POST', path='/api/ports',
            data={'serial': {'port': '/dev/ttyUSB0'}, 'servers': []})
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 400)

    def test_add_port_unknown_protocol(self):
        wrapper, _ = self._make_wrapper_with_ports()
        token = self._admin_token(wrapper)
        cfg = self._port_config()
        cfg['servers'][0]['protocol'] = 'unknown'
        client = self._auth_client(
            token, method='POST', path='/api/ports', data=cfg)
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 400)

    def test_add_port_socket_no_port_needed(self):
        wrapper, manager = self._make_wrapper_with_ports()
        token = self._admin_token(wrapper)
        cfg = {
            'serial': {'port': '/dev/ttyUSB0'},
            'servers': [{'protocol': 'socket', 'address': '/tmp/s.sock'}],
        }
        with patch.object(wrapper, '_create_proxy') as mock_create:
            mock_create.return_value = Mock()
            client = self._auth_client(
                token, method='POST', path='/api/ports', data=cfg)
            wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 201)

    def test_add_port_tcp_missing_port(self):
        wrapper, _ = self._make_wrapper_with_ports()
        token = self._admin_token(wrapper)
        cfg = {
            'serial': {'port': '/dev/ttyUSB0'},
            'servers': [{'protocol': 'tcp', 'address': '0.0.0.0'}],
        }
        client = self._auth_client(
            token, method='POST', path='/api/ports', data=cfg)
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 400)

    def test_update_port(self):
        cfg = self._port_config()
        wrapper, manager = self._make_wrapper_with_ports([cfg])
        token = self._admin_token(wrapper)
        new_cfg = self._port_config(baudrate=9600)
        with patch.object(wrapper, '_create_proxy') as mock_create:
            mock_create.return_value = Mock()
            client = self._auth_client(
                token, method='PUT', path='/api/ports/0', data=new_cfg)
            wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 200)
        manager.remove_server.assert_called_once()
        manager.add_server.assert_called_once()

    def test_update_port_not_found(self):
        wrapper, _ = self._make_wrapper_with_ports()
        token = self._admin_token(wrapper)
        cfg = self._port_config()
        client = self._auth_client(
            token, method='PUT', path='/api/ports/0', data=cfg)
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 404)

    def test_update_port_invalid_index(self):
        wrapper, _ = self._make_wrapper_with_ports()
        token = self._admin_token(wrapper)
        client = self._auth_client(
            token, method='PUT', path='/api/ports/abc', data={})
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 400)

    def test_delete_port(self):
        cfg = self._port_config()
        wrapper, manager = self._make_wrapper_with_ports([cfg])
        token = self._admin_token(wrapper)
        client = self._auth_client(
            token, method='DELETE', path='/api/ports/0')
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 200)
        manager.remove_server.assert_called_once()
        self.assertEqual(len(wrapper._serial_proxies), 0)

    def test_delete_port_not_found(self):
        wrapper, _ = self._make_wrapper_with_ports()
        token = self._admin_token(wrapper)
        client = self._auth_client(
            token, method='DELETE', path='/api/ports/0')
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 404)

    def test_add_port_non_admin(self):
        wrapper, _ = self._make_wrapper_with_ports()
        wrapper._auth.add_user('viewer', 'pass')
        login = MockClient(
            method='POST', path='/api/login',
            data={'login': 'viewer', 'password': 'pass'})
        wrapper._handle_request(login)
        token = login.responded['token']
        cfg = self._port_config()
        client = self._auth_client(
            token, method='POST', path='/api/ports', data=cfg)
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 403)

    def test_add_port_with_match(self):
        wrapper, manager = self._make_wrapper_with_ports()
        token = self._admin_token(wrapper)
        cfg = {
            'serial': {'match': {'vid': '0x303A'}, 'baudrate': 115200},
            'servers': [{'protocol': 'tcp', 'address': '0.0.0.0',
                'port': 10001}],
        }
        with patch.object(wrapper, '_create_proxy') as mock_create:
            mock_create.return_value = Mock()
            client = self._auth_client(
                token, method='POST', path='/api/ports', data=cfg)
            wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 201)

    def test_config_saved_after_add(self):
        wrapper, _ = self._make_wrapper_with_ports()
        token = self._admin_token(wrapper)
        cfg = self._port_config()
        with patch.object(wrapper, '_create_proxy') as mock_create, \
                patch.object(wrapper, '_save_config') as mock_save:
            mock_create.return_value = Mock()
            client = self._auth_client(
                token, method='POST', path='/api/ports', data=cfg)
            wrapper._handle_request(client)
        mock_save.assert_called_once()

    def test_config_saved_after_delete(self):
        cfg = self._port_config()
        wrapper, _ = self._make_wrapper_with_ports([cfg])
        token = self._admin_token(wrapper)
        with patch.object(wrapper, '_save_config') as mock_save:
            client = self._auth_client(
                token, method='DELETE', path='/api/ports/0')
            wrapper._handle_request(client)
        mock_save.assert_called_once()

    def test_old_proxy_closed_on_update(self):
        cfg = self._port_config()
        wrapper, _ = self._make_wrapper_with_ports([cfg])
        old_proxy = wrapper._serial_proxies[0]
        token = self._admin_token(wrapper)
        new_cfg = self._port_config(baudrate=9600)
        with patch.object(wrapper, '_create_proxy') as mock_create:
            mock_create.return_value = Mock()
            client = self._auth_client(
                token, method='PUT', path='/api/ports/0', data=new_cfg)
            wrapper._handle_request(client)
        old_proxy.close.assert_called_once()

    def test_old_proxy_closed_on_delete(self):
        cfg = self._port_config()
        wrapper, _ = self._make_wrapper_with_ports([cfg])
        old_proxy = wrapper._serial_proxies[0]
        token = self._admin_token(wrapper)
        client = self._auth_client(
            token, method='DELETE', path='/api/ports/0')
        wrapper._handle_request(client)
        old_proxy.close.assert_called_once()


class TestControlValidation(unittest.TestCase):
    """Tests for control config validation in port API"""

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

    def _make_wrapper(self):
        auth = self._auth_config()
        configuration = {
            'http': [{'address': '127.0.0.1', 'port': 0}],
            'users': auth['users'],
            'ports': [],
        }
        manager = Mock()
        with patch('ser2tcp.http_server._uhttp_server.HttpServer'):
            wrapper = HttpServerWrapper(
                {'address': '127.0.0.1', 'port': 0}, [],
                log=Mock(), configuration=configuration,
                server_manager=manager)
        return wrapper

    def test_add_port_with_control(self):
        wrapper = self._make_wrapper()
        token = self._admin_token(wrapper)
        cfg = {
            'serial': {'port': '/dev/ttyUSB0'},
            'servers': [{'protocol': 'tcp', 'address': '0.0.0.0',
                'port': 10001,
                'control': {'signals': ['rts', 'dtr', 'cts']}}],
        }
        with patch.object(wrapper, '_create_proxy') as mock_create:
            mock_create.return_value = Mock()
            client = MockClient(
                method='POST', path='/api/ports', data=cfg,
                headers={'authorization': f'Bearer {token}'})
            wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 201)

    def test_control_rejected_for_telnet(self):
        wrapper = self._make_wrapper()
        token = self._admin_token(wrapper)
        cfg = {
            'serial': {'port': '/dev/ttyUSB0'},
            'servers': [{'protocol': 'telnet', 'address': '0.0.0.0',
                'port': 10001,
                'control': {'signals': ['cts']}}],
        }
        client = MockClient(
            method='POST', path='/api/ports', data=cfg,
            headers={'authorization': f'Bearer {token}'})
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 400)
        self.assertIn('TELNET', client.responded['error'])

    def test_control_unknown_signal(self):
        wrapper = self._make_wrapper()
        token = self._admin_token(wrapper)
        cfg = {
            'serial': {'port': '/dev/ttyUSB0'},
            'servers': [{'protocol': 'tcp', 'address': '0.0.0.0',
                'port': 10001,
                'control': {'signals': ['unknown']}}],
        }
        client = MockClient(
            method='POST', path='/api/ports', data=cfg,
            headers={'authorization': f'Bearer {token}'})
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 400)
        self.assertIn('Unknown signal', client.responded['error'])

    def test_signals_endpoint(self):
        proxy = Mock()
        proxy.name = 'test'
        proxy.is_connected = True
        proxy.get_signals.return_value = 0b000101  # rts + cts
        wrapper = make_wrapper(serial_proxies=[proxy])
        client = MockClient(path='/api/signals')
        wrapper._handle_request(client)
        self.assertEqual(client.respond_status, 200)
        self.assertEqual(len(client.responded), 1)
        signals = client.responded[0]['signals']
        self.assertTrue(signals['rts'])
        self.assertTrue(signals['cts'])
        self.assertFalse(signals['dtr'])

    def test_status_includes_control(self):
        proxy = Mock()
        proxy.name = 'test'
        proxy.is_connected = False
        proxy.serial_config = {'port': '/dev/ttyUSB0'}
        proxy.match = None
        server = Mock()
        server.protocol = 'TCP'
        server.config = {
            'address': '0.0.0.0', 'port': 10001,
            'control': {'signals': ['cts', 'dsr']},
        }
        server.control = {'signals': ['cts', 'dsr']}
        server.connections = []
        proxy.servers = [server]
        wrapper = make_wrapper(serial_proxies=[proxy])
        client = MockClient(path='/api/status')
        wrapper._handle_request(client)
        srv = client.responded['ports'][0]['servers'][0]
        self.assertEqual(srv['control'], {'signals': ['cts', 'dsr']})


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


class TestIpFilterValidation(unittest.TestCase):
    """Test IP filter validation in port config"""

    def test_allow_list_valid(self):
        wrapper = make_wrapper()
        result = wrapper._validate_port_config({
            'serial': {'port': '/dev/ttyUSB0'},
            'servers': [{
                'protocol': 'tcp',
                'port': 10001,
                'allow': ['192.168.1.0/24', '10.0.0.5'],
            }]
        })
        self.assertIsNone(result)

    def test_deny_list_valid(self):
        wrapper = make_wrapper()
        result = wrapper._validate_port_config({
            'serial': {'port': '/dev/ttyUSB0'},
            'servers': [{
                'protocol': 'tcp',
                'port': 10001,
                'deny': ['10.0.0.0/8'],
            }]
        })
        self.assertIsNone(result)

    def test_allow_and_deny_valid(self):
        wrapper = make_wrapper()
        result = wrapper._validate_port_config({
            'serial': {'port': '/dev/ttyUSB0'},
            'servers': [{
                'protocol': 'tcp',
                'port': 10001,
                'allow': ['192.168.0.0/16'],
                'deny': ['192.168.1.100'],
            }]
        })
        self.assertIsNone(result)

    def test_allow_not_list(self):
        wrapper = make_wrapper()
        result = wrapper._validate_port_config({
            'serial': {'port': '/dev/ttyUSB0'},
            'servers': [{
                'protocol': 'tcp',
                'port': 10001,
                'allow': '192.168.1.0/24',
            }]
        })
        self.assertEqual(result, 'allow must be a list')

    def test_deny_not_list(self):
        wrapper = make_wrapper()
        result = wrapper._validate_port_config({
            'serial': {'port': '/dev/ttyUSB0'},
            'servers': [{
                'protocol': 'tcp',
                'port': 10001,
                'deny': '10.0.0.0/8',
            }]
        })
        self.assertEqual(result, 'deny must be a list')

    def test_allow_entry_not_string(self):
        wrapper = make_wrapper()
        result = wrapper._validate_port_config({
            'serial': {'port': '/dev/ttyUSB0'},
            'servers': [{
                'protocol': 'tcp',
                'port': 10001,
                'allow': [123],
            }]
        })
        self.assertEqual(result, 'allow entries must be strings')

    def test_websocket_with_ip_filter(self):
        wrapper = make_wrapper()
        result = wrapper._validate_port_config({
            'serial': {'port': '/dev/ttyUSB0'},
            'servers': [{
                'protocol': 'websocket',
                'endpoint': 'test',
                'allow': ['192.168.1.0/24'],
            }]
        })
        self.assertIsNone(result)
