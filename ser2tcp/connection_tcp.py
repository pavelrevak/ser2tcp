"""Connection TCP"""

import ser2tcp.connection as _connection


class ConnectionTcp(_connection.Connection):
    """TCP connection"""
    def __init__(
            self, connection, ser, send_timeout=None, buffer_limit=None,
            log=None):
        super().__init__(connection, send_timeout, buffer_limit, log)
        self._serial = ser
        self._log.info("Client connected: %s:%d TCP", *self._addr)

    def on_received(self, data):
        """Received data from client"""
        if data:
            self._serial.send(data)
