"""Server"""

# pylint: disable=C0209

import socket as _socket
import logging as _logging
import ser2tcp.connection_tcp as _connection_tcp
import ser2tcp.connection_telnet as _connection_telnet
import ser2tcp.connection_unix as _connection_unix


class ConfigError(Exception):
    """Configuration error exception"""


class Server():
    """Server connection manager"""

    CONNECTIONS = {
        'TCP': _connection_tcp.ConnectionTcp,
        'TELNET': _connection_telnet.ConnectionTelnet,
        'UNIX': _connection_unix.ConnectionUnix,
    }

    def __init__(self, config, ser, log=None):
        self._log = log if log else _logging.Logger(self.__class__.__name__)
        self._config = config
        self._serial = ser
        self._connections = []
        self._protocol = self._config['protocol'].upper()
        self._socket = None
        if self._protocol == "UNIX":
            self._log.info(
                "  Server: %s %s",
                self._config['address'],
                self._protocol)
        else:
            self._log.info(
                "  Server: %s %d %s",
                self._config['address'],
                self._config['port'],
                self._protocol)
        if self._protocol not in self.CONNECTIONS:
            raise ConfigError('Unknown protocol %s' % self._protocol)
        if self._protocol == "UNIX":
            self._socket = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
            self._socket.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
            self._socket.bind(self._config['address'])
        else:
            self._socket = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM, _socket.IPPROTO_TCP)
            self._socket.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
            self._socket.bind((config['address'], config['port']))
        self._socket.listen(1)

    def __del__(self):
        self.close()

    def _client_connect(self):
        """connect to client, will accept waiting connection"""
        sock, addr = self._socket.accept()
        if not self._connections:
            if not self._serial.connect():
                self._log.info("Client canceled: %s:%d", *addr)
                sock.close()
                return
        connection = self.CONNECTIONS[self._protocol](
            connection=(sock, addr),
            ser=self._serial,
            log=self._log,
        )
        if self._serial.connect():
            self._connections.append(connection)
        else:
            connection.close()

    def close_connections(self):
        """close all clients"""
        while self._connections:
            self._connections.pop().close()

    def close(self):
        """Close socket and all connections"""
        if self._socket is not None:
            self.close_connections()
            self._socket.close()
            self._socket = None

    def has_connections(self):
        """True if server has some connections"""
        return bool(self._connections)

    def sockets(self):
        """Return socket from this server and all connected clients sockets"""
        sockets = [self._socket]
        for con in self._connections:
            sockets.append(con.socket())
        return sockets

    def socket_event(self, read_sockets):
        """Process sockets with read event"""
        if self._socket in read_sockets:
            self._client_connect()
        for con in self._connections:
            if con.socket() in read_sockets:
                data = b''
                try:
                    data = con.socket().recv(4096)
                    self._log.debug("(%s:%d): %s", *con.get_address(), data)
                except ConnectionResetError as err:
                    self._log.info("(%s:%d): %s", *con.get_address(), err)
                if not data:
                    con.close()
                    self._connections.remove(con)
                    if not self._connections:
                        self._serial.disconnect()
                    return
                con.on_received(data)

    def send(self, data):
        """Send data to connection"""
        for con in self._connections:
            con.send(data)
