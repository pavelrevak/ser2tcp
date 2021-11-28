"""Server"""

import logging as _logging
import serial as _serial
import ser2tcp.server as _server


class SerialProxy():
    """Serial connection manager"""
    PARITY_CONFIG = {
        'NONE': _serial.PARITY_NONE,
        'EVEN': _serial.PARITY_EVEN,
        'ODD': _serial.PARITY_ODD,
        'MARK': _serial.PARITY_MARK,
        'SPACE': _serial.PARITY_SPACE,
    }
    STOPBITS_CONFIG = {
        'ONE': _serial.STOPBITS_ONE,
        'ONE_POINT_FIVE': _serial.STOPBITS_ONE_POINT_FIVE,
        'TWO': _serial.STOPBITS_TWO,
    }
    BYTESIZE_CONFIG = {
        'FIVEBITS': _serial.FIVEBITS,
        'SIXBITS': _serial.SIXBITS,
        'SEVENBITS': _serial.SEVENBITS,
        'EIGHTBITS': _serial.EIGHTBITS,
    }

    def __init__(self, config, log=None):
        self._log = log if log else _logging.Logger(self.__class__.__name__)
        self._serial = None
        self._servers = []
        self._serial_config = self.fix_serial_config(config['serial'])
        self._log.info(
            "Serial: %s %d",
            self._serial_config['port'],
            self._serial_config['baudrate'])
        for server_config in config['servers']:
            self._servers.append(_server.Server(server_config, self, log))

    def fix_serial_config(self, config):
        """Fix serial configuration"""
        if 'parity' in config:
            for key, val in self.PARITY_CONFIG.items():
                if config['parity'] == key:
                    config['parity'] = val
        if 'stopbits' in config:
            for key, val in self.STOPBITS_CONFIG.items():
                if config['stopbits'] == key:
                    config['stopbits'] = val
        if 'bygesize' in config:
            for key, val in self.STOPBITS_CONFIG.items():
                if config['bytesize'] == key:
                    config['bytesize'] = val
        return config

    def __del__(self):
        self.close()

    def connect(self):
        """Connect to serial port"""
        if not self._serial:
            try:
                self._serial = _serial.Serial(**self._serial_config)
            except (_serial.SerialException, OSError) as err:
                self._log.warning(err)
                return False
            self._log.info(
                "Serial %s connected", self._serial_config['port'])
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
            self._log.info(
                "Serial %s disconnected", self._serial_config['port'])

    def close(self):
        """Close socket and all connections"""
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
                self._log.debug("(%s): %s", self._serial_config['port'], data)
                self.send_to_connections(data)
            except _serial.SerialException:
                for server in self._servers:
                    server.close_connections()
                self.disconnect()
                return

    def send(self, data):
        """Send data to serial port"""
        if self._serial:
            self._serial.write(data)
