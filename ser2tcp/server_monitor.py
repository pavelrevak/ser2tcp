"""WebSocket monitor server - read-only serial communication monitoring"""

import logging as _logging


class ServerMonitor():
    """WebSocket virtual server for monitoring serial communication.

    Read-only - receives TX/RX data with direction prefix.
    Protocol: binary frames with 1-byte prefix (0x01=TX, 0x02=RX).
    """

    DIR_TX = 1
    DIR_RX = 2

    def __init__(self, serial_proxy, log=None):
        self._log = log if log else _logging.Logger(self.__class__.__name__)
        self._serial = serial_proxy
        self._connections = []

    @property
    def connections(self):
        """Return list of connections"""
        return self._connections

    def add_connection(self, client):
        """Add WebSocket connection and register as monitor"""
        self._connections.append(client)
        if len(self._connections) == 1:
            self._serial.add_monitor(self._on_data)
            self._log.debug("Monitor callback registered for %s", self._serial.name)
        addr = self._client_addr(client)
        self._log.info(
            "Monitor connected: %s /ws/monitor/%s",
            addr, self._serial.name)

    def remove_connection(self, client):
        """Remove WebSocket connection"""
        if client in self._connections:
            addr = self._client_addr(client)
            self._connections.remove(client)
            self._log.info("Monitor disconnected: %s", addr)
            if not self._connections:
                self._serial.remove_monitor(self._on_data)

    def process_message(self, client):
        """Ignore incoming messages - monitor is read-only"""
        pass

    def _on_data(self, direction, data):
        """Monitor callback - send data with direction prefix"""
        frame = bytes([direction]) + data
        self._log.debug("Monitor sending: dir=%d len=%d", direction, len(data))
        for client in list(self._connections):
            try:
                client.ws_send(frame)
            except OSError:
                self.remove_connection(client)

    def process_stale(self):
        """Remove closed connections"""
        for client in list(self._connections):
            if not client.is_websocket or client.socket is None:
                self.remove_connection(client)

    def close(self):
        """Close all connections"""
        while self._connections:
            client = self._connections.pop()
            try:
                client.ws_close(1001, 'Server shutting down')
            except OSError:
                pass
        self._serial.remove_monitor(self._on_data)

    def _client_addr(self, client):
        """Return formatted client address string"""
        try:
            addr = client.addr
            if isinstance(addr, tuple) and len(addr) >= 2:
                return "%s:%d" % (addr[0], addr[1])
            return str(addr)
        except Exception:
            return 'unknown'
