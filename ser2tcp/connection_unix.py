"""Connection Unix"""

import ser2tcp.connection as _connection


class ConnectionUnix(_connection.Connection):
    """Unix connection"""
    def __init__(self, connection, ser, log=None):
        super().__init__(connection, log)
        self._serial = ser
        self._log.info("Client connected: %s:%d UNIX", *self._addr)

    @staticmethod
    def list_pull_first(data):
        """get first entry from array"""
        dat = data[0]
        del data[0]
        return dat

    def on_received(self, data):
        """Received data from client"""
        if data:
            print(data)
            self._serial.send(data)
