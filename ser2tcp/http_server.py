"""HTTP server integration with uhttp"""

import json as _json
import logging as _logging
import pathlib as _pathlib
import ssl as _ssl

import serial.tools.list_ports as _list_ports

import uhttp.server as _uhttp_server

import ser2tcp.http_auth as _http_auth
import ser2tcp.serial_proxy as _serial_proxy

HTML_DIR = _pathlib.Path(__file__).parent / 'html'


class HttpServerWrapper():
    """Wrapper around uhttp.HttpServer compatible with ServersManager"""

    def __init__(self, configs, serial_proxies, log=None,
            config_path=None, configuration=None,
            server_manager=None):
        self._log = log if log else _logging.getLogger(__name__)
        self._serial_proxies = serial_proxies
        self._server_manager = server_manager
        self._config_path = config_path
        self._configuration = configuration if configuration else {}
        if isinstance(configs, dict):
            configs = [configs]
        # Auth config at root level (users, tokens, session_timeout)
        # Migrate from old format (auth inside http config) if needed
        auth_config = {}
        if self._configuration.get('users'):
            auth_config['users'] = self._configuration['users']
        if self._configuration.get('tokens'):
            auth_config['tokens'] = self._configuration['tokens']
        if 'session_timeout' in self._configuration:
            auth_config['session_timeout'] = self._configuration['session_timeout']
        # Backward compatibility: migrate auth from http config to root
        if not auth_config:
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

    def _error(self, client, error, status):
        """Log warning and send error response"""
        self._log.warning("%s", error)
        client.respond({'error': error}, status=status)

    def _require_auth(self, client):
        """Check authentication, return user info or None (sends 401)"""
        if not self._auth or self._auth.is_empty:
            return {'login': None, 'admin': True}
        token = self._get_bearer_token(client)
        if not token:
            self._error(client, 'Authorization required', 401)
            return None
        user = self._auth.authenticate(token)
        if not user:
            self._error(client, 'Invalid or expired token', 401)
            return None
        return user

    def _handle_request(self, client):
        """Handle HTTP request"""
        if self._log.isEnabledFor(_logging.INFO):
            self._log.info("%s %s", client.method, client.path)
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
        elif client.method == 'GET' and client.path == '/api/detect':
            self._handle_api_detect(client)
        elif client.path == '/api/ports':
            if client.method == 'POST':
                self._handle_api_ports_add(client, user)
            else:
                self._error(client, 'Method not allowed', 405)
        elif client.path.startswith('/api/ports/'):
            self._route_api_ports_item(client, user)
        elif client.path == '/api/users':
            if client.method == 'GET':
                self._handle_api_users_list(client)
            elif client.method == 'POST':
                self._handle_api_users_add(client, user)
            else:
                self._error(client, 'Method not allowed', 405)
        elif client.path.startswith('/api/users/'):
            login = client.path[len('/api/users/'):]
            if client.method == 'PUT':
                self._handle_api_users_update(client, user, login)
            elif client.method == 'DELETE':
                self._handle_api_users_delete(client, user, login)
            else:
                self._error(client, 'Method not allowed', 405)
        else:
            self._error(client, 'Not found', 404)

    def _handle_static(self, client):
        """Serve static files from html directory"""
        path = client.path.lstrip('/')
        if not path:
            path = 'index.html'
        file_path = (HTML_DIR / path).resolve()
        if not str(file_path).startswith(str(HTML_DIR)):
            self._error(client, 'Not found', 404)
            return
        if not file_path.is_file():
            self._error(client, 'Not found', 404)
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

    def _handle_api_detect(self, client):
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

    def _save_config(self):
        """Save configuration to config file"""
        if not self._config_path or not self._configuration:
            return
        with open(self._config_path, 'w', encoding='utf-8') as f:
            _json.dump(self._configuration, f, indent=4)
            f.write('\n')

    def _get_ports_config(self):
        """Get ports list from configuration"""
        ports = self._configuration.get('ports', [])
        if isinstance(self._configuration, list):
            ports = self._configuration
        return ports

    def _route_api_ports_item(self, client, user):
        """Route /api/ports/<index> requests"""
        try:
            index = int(client.path[len('/api/ports/'):])
        except ValueError:
            self._error(client, 'Invalid port index', 400)
            return
        if client.method == 'PUT':
            self._handle_api_ports_update(client, user, index)
        elif client.method == 'DELETE':
            self._handle_api_ports_delete(client, user, index)
        else:
            self._error(client, 'Method not allowed', 405)

    def _validate_port_config(self, data):
        """Validate port configuration, return error string or None"""
        if not isinstance(data, dict):
            return 'Invalid request'
        if 'serial' not in data:
            return 'serial config required'
        serial = data['serial']
        if not isinstance(serial, dict):
            return 'Invalid serial config'
        if 'port' not in serial and 'match' not in serial:
            return "serial config must have 'port' or 'match'"
        if 'servers' not in data or not isinstance(data['servers'], list):
            return 'servers list required'
        if not data['servers']:
            return 'At least one server required'
        for srv in data['servers']:
            if not isinstance(srv, dict):
                return 'Invalid server config'
            if 'protocol' not in srv:
                return 'Server protocol required'
            proto = srv['protocol'].upper()
            if proto not in ('TCP', 'TELNET', 'SSL', 'SOCKET'):
                return f'Unknown protocol: {srv["protocol"]}'
            if proto == 'SOCKET':
                if 'address' not in srv:
                    return 'Socket path (address) required'
            else:
                if 'port' not in srv:
                    return 'Server port required'
        return None

    def _create_proxy(self, config):
        """Create SerialProxy from config"""
        proxy = _serial_proxy.SerialProxy(config, self._log)
        return proxy

    def _handle_api_ports_add(self, client, user):
        """Add new port configuration"""
        if not self._require_admin(client, user):
            return
        data = client.data
        error = self._validate_port_config(data)
        if error:
            self._error(client, error, 400)
            return
        try:
            proxy = self._create_proxy(data)
        except (ValueError, KeyError) as err:
            self._error(client, str(err), 400)
            return
        self._serial_proxies.append(proxy)
        if self._server_manager:
            self._server_manager.add_server(proxy)
        ports = self._get_ports_config()
        ports.append(data)
        if 'ports' not in self._configuration:
            self._configuration['ports'] = ports
        self._save_config()
        self._log.info("Port added: %d", len(self._serial_proxies) - 1)
        client.respond({'ok': True, 'index': len(self._serial_proxies) - 1},
            status=201)

    def _handle_api_ports_update(self, client, user, index):
        """Update port configuration"""
        if not self._require_admin(client, user):
            return
        ports = self._get_ports_config()
        if index < 0 or index >= len(ports):
            self._error(client, 'Port not found', 404)
            return
        data = client.data
        error = self._validate_port_config(data)
        if error:
            self._error(client, error, 400)
            return
        try:
            new_proxy = self._create_proxy(data)
        except (ValueError, KeyError) as err:
            self._error(client, str(err), 400)
            return
        # Replace old proxy
        old_proxy = self._serial_proxies[index]
        old_proxy.close()
        if self._server_manager:
            self._server_manager.remove_server(old_proxy)
            self._server_manager.add_server(new_proxy)
        self._serial_proxies[index] = new_proxy
        ports[index] = data
        self._save_config()
        self._log.info("Port updated: %d", index)
        client.respond({'ok': True})

    def _handle_api_ports_delete(self, client, user, index):
        """Delete port configuration"""
        if not self._require_admin(client, user):
            return
        ports = self._get_ports_config()
        if index < 0 or index >= len(ports):
            self._error(client, 'Port not found', 404)
            return
        old_proxy = self._serial_proxies[index]
        old_proxy.close()
        if self._server_manager:
            self._server_manager.remove_server(old_proxy)
        del self._serial_proxies[index]
        del ports[index]
        self._save_config()
        self._log.info("Port deleted: %d", index)
        client.respond({'ok': True})

    def _handle_api_login(self, client):
        """Authenticate user and return session token"""
        if not self._auth:
            self._error(client, 'Auth not configured', 404)
            return
        data = client.data
        if not isinstance(data, dict):
            self._error(client, 'Invalid request', 400)
            return
        login = data.get('login', '')
        password = data.get('password', '')
        token = self._auth.login(login, password)
        if not token:
            self._error(client, f'Login failed: {login}', 401)
            return
        self._log.info("Login: %s", login)
        client.respond({'token': token})

    def _handle_api_logout(self, client):
        """Invalidate session"""
        if not self._auth:
            self._error(client, 'Auth not configured', 404)
            return
        token = self._get_bearer_token(client)
        if token:
            self._auth.logout(token)
        client.respond({'ok': True})

    def _require_admin(self, client, user):
        """Check if user is admin, send 403 if not"""
        if not user.get('admin'):
            self._error(client, 'Admin access required', 403)
            return False
        return True

    def _ensure_auth(self):
        """Create auth if not exists, return SessionManager"""
        if not self._auth:
            self._auth = _http_auth.SessionManager({})
        return self._auth

    def _save_auth_config(self):
        """Save auth config to config file (users, tokens at root level)"""
        if not self._config_path or not self._configuration:
            return
        auth_config = self._auth.get_auth_config()
        # Save at root level
        if auth_config.get('users'):
            self._configuration['users'] = auth_config['users']
        elif 'users' in self._configuration:
            del self._configuration['users']
        if auth_config.get('tokens'):
            self._configuration['tokens'] = auth_config['tokens']
        elif 'tokens' in self._configuration:
            del self._configuration['tokens']
        if 'session_timeout' in auth_config:
            self._configuration['session_timeout'] = auth_config['session_timeout']
        # Remove old auth from http configs (migration)
        http_configs = self._configuration.get('http', [])
        if isinstance(http_configs, dict):
            http_configs = [http_configs]
        for config in http_configs:
            config.pop('auth', None)
        self._save_config()

    def _handle_api_users_list(self, client):
        """List users (without passwords)"""
        if not self._auth:
            client.respond([])
            return
        client.respond(self._auth.list_users())

    def _handle_api_users_add(self, client, user):
        """Add new user"""
        if not self._require_admin(client, user):
            return
        data = client.data
        if not isinstance(data, dict) or 'login' not in data \
                or 'password' not in data:
            self._error(client, 'login and password required', 400)
            return
        kwargs = {}
        if 'admin' in data:
            kwargs['admin'] = bool(data['admin'])
        if 'session_timeout' in data:
            kwargs['session_timeout'] = data['session_timeout']
        auth = self._ensure_auth()
        is_first = auth.is_empty
        if not auth.add_user(data['login'], data['password'], **kwargs):
            self._error(client, 'User already exists', 400)
            return
        self._save_auth_config()
        self._log.info("User added: %s", data['login'])
        if is_first:
            token = auth.create_session(data['login'])
            client.respond({'ok': True, 'token': token}, status=201)
        else:
            client.respond({'ok': True}, status=201)

    def _handle_api_users_update(self, client, user, login):
        """Update existing user"""
        if not self._auth:
            self._error(client, 'User not found', 404)
            return
        if not self._require_admin(client, user):
            return
        data = client.data
        if not isinstance(data, dict):
            self._error(client, 'Invalid request', 400)
            return
        kwargs = {}
        if 'password' in data:
            kwargs['password'] = data['password']
        if 'admin' in data:
            kwargs['admin'] = bool(data['admin'])
        if 'session_timeout' in data:
            kwargs['session_timeout'] = data['session_timeout']
        result = self._auth.update_user(login, **kwargs)
        if result is False:
            self._error(client, 'User not found', 404)
            return
        if isinstance(result, str):
            self._error(client, result, 400)
            return
        self._save_auth_config()
        self._log.info("User updated: %s", login)
        client.respond({'ok': True})

    def _handle_api_users_delete(self, client, user, login):
        """Delete user"""
        if not self._auth:
            self._error(client, 'User not found', 404)
            return
        if not self._require_admin(client, user):
            return
        result = self._auth.delete_user(login)
        if result is False:
            self._error(client, 'User not found', 404)
            return
        if isinstance(result, str):
            self._error(client, result, 400)
            return
        self._save_auth_config()
        self._log.info("User deleted: %s", login)
        client.respond({'ok': True})
