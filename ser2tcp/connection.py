"""Connection"""

import logging as _logging
from typing import Tuple


class Connection():
    """Connection"""
    def __init__(
            self,
            connection: Tuple[str, int],
            log_global: _logging.Logger,
            log_serial: _logging.Logger
        ):
        self._socket, self._addr = connection
        self._log_global = log_global
        self._log_serial = log_serial

    def __del__(self):
        self.close()

    def socket(self):
        """Return reference to socket"""
        return self._socket

    def close(self):
        """Close connection"""
        if self._socket:
            self._socket.close()
            self._socket = None
            ip, port = self._addr
            self._log_global.info(f"Client disconnected: {ip}:{port}")
            self._log_serial.info(f"Client disconnected: {ip}:{port}")

    def fileno(self):
        """emulate fileno method of socket"""
        return self._socket.fileno() if self._socket else None

    def get_address(self):
        """Return address"""
        return self._addr

    def send(self, data):
        """Send data to client"""
        self._socket.sendall(data)
