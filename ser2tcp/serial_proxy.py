"""Server"""

import logging as _logging
import serial as _serial

import ser2tcp.server as _server
import ser2tcp.conf_models as _conf_models


class SerialProxy():
    """Serial connection manager"""

    def __init__(
            self,
            config: _conf_models.SerialMappingInstance,
            log_global: _logging.Logger,
            log_serial: _logging.Logger,
        ):
        self._log_global = log_global
        self._log_serial = log_serial
        self._conf = config
        self._serial = None
        self._servers = []
        self._log_global.info(f"Serial: {self._conf.serial.port} {self._conf.serial.baudrate}")
        self._log_serial.info(f"Serial: {self._conf.serial.port} {self._conf.serial.baudrate}")
        
        for server_config in self._conf.servers:
            self._servers.append(
                _server.Server(server_config, self, self._log_global, self._log_serial)
            )

    def __del__(self):
        self.close()

    def connect(self):
        """Connect to serial port"""
        if not self._serial:
            try:
                self._serial = _serial.Serial(**self._conf.serial.dict())
            except (_serial.SerialException, OSError) as err:
                self._log_global.warning(err)
                return False
            self._log_global.info(f"Serial {self._conf.serial.port}: connected")
            self._log_serial.info(f"Serial {self._conf.serial.port}: connected")
        return True

    def has_connections(self):
        """Check if there are any active connections"""
        for server in self._servers:
            if server.has_connections():
                return True
        return False

    def disconnect(self):
        """Disconnect serial port, but if there are no active connections"""
        if self._serial and not self.has_connections():
            self._serial.close()
            self._serial = None
            self._log_global.info(f"Serial {self._conf.serial.port}: disconnected")
            self._log_serial.info(f"Serial {self._conf.serial.port}: disconnected")

    def close(self):
        """Close socket and all connections"""

        self._log_global.info(f"Serial {self._conf.serial.port}: Closing all serial connections")
        self._log_serial.info(f"Serial {self._conf.serial.port}: Closing all serial connections")
        while self._servers:
            self._servers.pop().close()
        self.disconnect()

    def sockets(self):
        """Return all sockets from this server"""
        sockets = []
        for server in self._servers:
            sockets += server.sockets()
        if self._serial:
            sockets.append(self._serial)
        return sockets

    def send_to_connections(self, data):
        """Send data to all connections"""
        for server in self._servers:
            server.send(data)

    def socket_event(self, read_sockets):
        """Process sockets with read event"""
        for server in self._servers:
            server.socket_event(read_sockets)
        if self._serial and self._serial in read_sockets:
            try:
                data = self._serial.read(size=self._serial.in_waiting)
                self._log_global.debug(f"({self._conf.serial.port}): {data}")
                self._log_serial.debug(f"({self._conf.serial.port}): {data}")
                self.send_to_connections(data)
            except (OSError, _serial.SerialException) as err:
                self._log_global.warning(f"({self._conf.serial.port}):{err}")
                self._log_serial.warning(f"({self._conf.serial.port}):{err}")
                for server in self._servers:
                    server.close_connections()
                self.disconnect()
                return

    def send(self, data):
        """Send data to serial port"""
        if self._serial:
            self._serial.write(data)
