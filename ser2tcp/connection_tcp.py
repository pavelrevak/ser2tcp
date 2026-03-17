"""Connection TCP"""

import ser2tcp.connection as _connection


class ConnectionTcp(_connection.Connection):
    """TCP connection"""
    def __init__(self, connection, ser, log=None):
        super().__init__(connection, log)
        self._serial = ser
        self._log.info("Client connected: %s:%d TCP", *self._addr)

    def on_received(self, data):
        """Received data from client"""
        if data:
            self._serial.send(data)
