"""HTTP server integration with uhttp"""

import logging as _logging
import pathlib as _pathlib
import ssl as _ssl

import serial.tools.list_ports as _list_ports

import uhttp.server as _uhttp_server

import ser2tcp.http_auth as _http_auth

HTML_DIR = _pathlib.Path(__file__).parent / 'html'


class HttpServerWrapper():
    """Wrapper around uhttp.HttpServer compatible with ServersManager"""

    def __init__(self, configs, serial_proxies, log=None):
        self._log = log if log else _logging.getLogger(__name__)
        self._serial_proxies = serial_proxies
        if isinstance(configs, dict):
            configs = [configs]
        # Auth config is shared across all HTTP servers
        auth_config = None
        for config in configs:
            if 'auth' in config:
                auth_config = config['auth']
                break
        self._auth = _http_auth.SessionManager(auth_config) if auth_config else None
        self._servers = []
        for config in configs:
            address = config.get('address', '0.0.0.0')
            port = config.get('port', 8080)
            ssl_context = None
            if 'ssl' in config:
                ssl_config = config['ssl']
                ssl_context = _ssl.SSLContext(_ssl.PROTOCOL_TLS_SERVER)
                ssl_context.load_cert_chain(
                    ssl_config['certfile'], ssl_config['keyfile'])
                self._log.info(
                    "HTTPS server: %s:%d", address, port)
            else:
                self._log.info(
                    "HTTP server: %s:%d", address, port)
            self._servers.append(_uhttp_server.HttpServer(
                address=address, port=port, ssl_context=ssl_context))

    def read_sockets(self):
        """Return sockets for reading"""
        sockets = []
        for server in self._servers:
            sockets.extend(server.read_sockets)
        return sockets

    def write_sockets(self):
        """Return sockets for writing"""
        sockets = []
        for server in self._servers:
            sockets.extend(server.write_sockets)
        return sockets

    def process_read(self, read_sockets):
        """Process read events"""
        for server in self._servers:
            client = server.process_events(read_sockets, [])
            if client:
                self._handle_request(client)

    def process_write(self, write_sockets):
        """Process write events"""
        for server in self._servers:
            server.process_events([], write_sockets)

    def process_stale(self):
        """Cleanup expired sessions"""
        if self._auth:
            self._auth.cleanup()

    def close(self):
        """Close all HTTP servers"""
        for server in self._servers:
            server.close()

    def _get_bearer_token(self, client):
        """Extract token from Authorization header or query parameter"""
        auth = client.headers.get('authorization', '')
        if auth.startswith('Bearer '):
            return auth[7:]
        if client.query:
            return client.query.get('token')
        return None

    def _require_auth(self, client):
        """Check authentication, return user info or None (sends 401)"""
        if not self._auth:
            return {'login': None, 'admin': True}
        token = self._get_bearer_token(client)
        if not token:
            client.respond({'error': 'Authorization required'}, status=401)
            return None
        user = self._auth.authenticate(token)
        if not user:
            client.respond({'error': 'Invalid or expired token'}, status=401)
            return None
        return user

    def _handle_request(self, client):
        """Handle HTTP request"""
        # Login endpoint - no auth required
        if client.method == 'POST' and client.path == '/api/login':
            self._handle_api_login(client)
            return
        # Logout endpoint
        if client.method == 'POST' and client.path == '/api/logout':
            self._handle_api_logout(client)
            return
        # Static files - no auth
        if client.method == 'GET' and not client.path.startswith('/api/'):
            self._handle_static(client)
            return
        # All API endpoints require auth
        user = self._require_auth(client)
        if not user:
            return
        if client.method == 'GET' and client.path == '/api/status':
            self._handle_api_status(client)
        elif client.method == 'GET' and client.path == '/api/ports':
            self._handle_api_ports(client)
        else:
            client.respond({'error': 'Not found'}, status=404)

    def _handle_static(self, client):
        """Serve static files from html directory"""
        path = client.path.lstrip('/')
        if not path:
            path = 'index.html'
        file_path = (HTML_DIR / path).resolve()
        if not str(file_path).startswith(str(HTML_DIR)):
            client.respond('Not Found', status=404)
            return
        if not file_path.is_file():
            client.respond('Not Found', status=404)
            return
        client.respond_file(str(file_path))

    def _handle_api_status(self, client):
        """Return runtime status with connections"""
        ports = []
        for proxy in self._serial_proxies:
            serial_cfg = proxy.serial_config
            serial_info = {
                'port': serial_cfg.get('port'),
                'connected': proxy.is_connected,
            }
            if 'baudrate' in serial_cfg:
                serial_info['baudrate'] = serial_cfg['baudrate']
            port_info = {'serial': serial_info}
            if proxy.match:
                port_info['serial']['match'] = proxy.match
            servers = []
            for server in proxy.servers:
                srv_info = {
                    'protocol': server.protocol,
                    'address': server.config['address'],
                    'connections': [
                        {'address': con.address_str()}
                        for con in server.connections
                    ],
                }
                if server.protocol != 'SOCKET':
                    srv_info['port'] = server.config['port']
                servers.append(srv_info)
            port_info['servers'] = servers
            ports.append(port_info)
        client.respond({'ports': ports})

    def _handle_api_ports(self, client):
        """Return list of available serial ports"""
        ports = []
        for port in _list_ports.comports():
            info = {'device': port.device}
            if port.description and port.description != 'n/a':
                info['description'] = port.description
            if port.hwid and port.hwid != 'n/a':
                info['hwid'] = port.hwid
            if port.vid is not None:
                info['vid'] = f'0x{port.vid:04X}'
                info['pid'] = f'0x{port.pid:04X}'
                if port.serial_number:
                    info['serial_number'] = port.serial_number
                if port.manufacturer:
                    info['manufacturer'] = port.manufacturer
                if port.product:
                    info['product'] = port.product
                if port.location:
                    info['location'] = port.location
            ports.append(info)
        client.respond(ports)

    def _handle_api_login(self, client):
        """Authenticate user and return session token"""
        if not self._auth:
            client.respond({'error': 'Auth not configured'}, status=404)
            return
        data = client.data
        if not isinstance(data, dict):
            client.respond({'error': 'Invalid request'}, status=400)
            return
        login = data.get('login', '')
        password = data.get('password', '')
        token = self._auth.login(login, password)
        if not token:
            self._log.info("Login failed: %s", login)
            client.respond({'error': 'Invalid credentials'}, status=401)
            return
        self._log.info("Login: %s", login)
        client.respond({'token': token})

    def _handle_api_logout(self, client):
        """Invalidate session"""
        if not self._auth:
            client.respond({'error': 'Auth not configured'}, status=404)
            return
        token = self._get_bearer_token(client)
        if token:
            self._auth.logout(token)
        client.respond({'ok': True})
