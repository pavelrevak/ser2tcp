"""Connection"""

import logging as _logging
import time as _time


class Connection():
    """Connection"""

    DEFAULT_SEND_TIMEOUT = 5.0
    DEFAULT_BUFFER_LIMIT = None

    def __init__(
            self, connection, send_timeout=None, buffer_limit=None,
            log=None):
        self._log = log if log else _logging.Logger(self.__class__.__name__)
        self._socket, self._addr = connection
        self._out_buffer = bytearray()
        self._last_write_time = _time.time()
        if send_timeout is not None:
            self._send_timeout = send_timeout
        else:
            self._send_timeout = self.DEFAULT_SEND_TIMEOUT
        if buffer_limit is not None:
            self._buffer_limit = buffer_limit
        else:
            self._buffer_limit = self.DEFAULT_BUFFER_LIMIT

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
            self._log.info("Client disconnected: %s", self.address_str())

    def fileno(self):
        """emulate fileno method of socket"""
        return self._socket.fileno() if self._socket else None

    def get_address(self):
        """Return address"""
        return self._addr

    def address_str(self):
        """Return formatted address string"""
        return "%s:%d" % self._addr

    def send(self, data):
        """Add data to output buffer, return number of bytes added"""
        if not self._socket:
            return None
        new_size = len(self._out_buffer) + len(data)
        if self._buffer_limit and new_size > self._buffer_limit:
            return None
        if not self._out_buffer:
            # Reset timeout when buffer becomes non-empty
            self._last_write_time = _time.time()
        self._out_buffer.extend(data)
        return len(data)

    def flush(self):
        """Flush output buffer, return number of bytes sent or None on error"""
        if not self._socket or not self._out_buffer:
            return 0
        try:
            sent = self._socket.send(self._out_buffer)
            if sent > 0:
                del self._out_buffer[:sent]
                self._last_write_time = _time.time()
            return sent
        except OSError:
            return None

    def has_pending_data(self):
        """Return True if there is data in output buffer"""
        return bool(self._out_buffer)

    def is_stale(self):
        """Return True if send timeout expired"""
        if not self._out_buffer:
            return False
        return _time.time() - self._last_write_time > self._send_timeout
