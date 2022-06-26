"""Server"""

# pylint: disable=C0209
from __future__ import annotations

import logging as _logging
import socket as _socket

import ser2tcp.conf_models as _conf_models
import ser2tcp.serial_proxy as _serial_proxy


class Server():
    """Server connection manager"""

    def __init__(
            self,
            config: _conf_models.ServerInstance,
            ser: _serial_proxy.SerialProxy,
            log_global: _logging.Logger,
            log_serial: _logging.Logger,
        ):
        self._log_global = log_global
        self._log_serial = log_serial
        self._config = config
        self._serial = ser
        self._connections = []
        self._socket = None

        self._log_global.info("-> Starting server: {} {} {}".format(
            self._config.address,
            self._config.port,
            self._config.protocol,
        ))
        self._log_serial.info("-> Starting server: {} {} {}".format(
            self._config.address,
            self._config.port,
            self._config.protocol,
        ))

        self._socket = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM, _socket.IPPROTO_TCP)
        self._socket.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
        self._socket.bind((self._config.address, self._config.port))
        self._socket.listen(1)

    def __del__(self):
        self.close()

    def _client_connect(self):
        """connect to client, will accept waiting connection"""
        sock, addr = self._socket.accept()
        if not self._connections:
            if not self._serial.connect():
                self._log_global.info(f"Client canceled: {addr[0]}:{addr[1]}")
                self._log_serial.info(f"Client canceled: {addr[0]}:{addr[1]}")
                sock.close()
                return

        # create a TCP or TELNET connection
        connection = self._config.protocol(
            connection=(sock, addr),
            ser=self._serial,
            log_global=self._log_global,
            log_serial=self._log_serial,
        )

        if self._serial.connect():
            self._connections.append(connection)
            self._log_global.info(f"Serial {self._serial._conf.serial.port}: Client added: {addr[0]}:{addr[1]}")
            self._log_serial.info(f"Serial {self._serial._conf.serial.port}: Client added: {addr[0]}:{addr[1]}")
        else:
            connection.close()
            self._log_global.info(f"Serial {self._serial._conf.serial.port}: Refusing Client (no serial port open): {addr[0]}:{addr[1]}")
            self._log_serial.info(f"Serial {self._serial._conf.serial.port}: Refusing Client (no serial port open): {addr[0]}:{addr[1]}")

    def close_connections(self):
        """close all clients"""
        self._log_global.info(f"Serial {self._serial._conf.serial.port}: Closing all server connections.")
        self._log_serial.info(f"Serial {self._serial._conf.serial.port}: Closing all server connections.")
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
                    ip, port = con.get_address()
                    self._log_global.debug(f"Serial {self._serial._conf.serial.port}: ({ip}:{port}): {data}")
                    self._log_serial.debug(f"Serial {self._serial._conf.serial.port}: ({ip}:{port}): {data}")
                except ConnectionResetError as err:
                    self._log_global.info(f"Serial {self._serial._conf.serial.port}: ({ip}:{port}): {err}")
                    self._log_serial.info(f"Serial {self._serial._conf.serial.port}: ({ip}:{port}): {err}")
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
