"""Connection"""

import logging as _logging


class Connection():
    """Connection"""
    def __init__(self, connection, log=None):
        self._log = log if log else _logging.Logger(self.__class__.__name__)
        self._socket, self._addr = connection

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
            self._log.info("Client disconnected: %s:%d", *self._addr)

    def fileno(self):
        """emulate fileno method of socket"""
        return self._socket.fileno() if self._socket else None

    def get_address(self):
        """Return address"""
        return self._addr

    def send(self, data):
        """Send data to client"""
        self._socket.sendall(data)
