"""Ser2tcp
Simple proxy for connecting over TCP or telnet to serial port
"""

import sys
import select
import socket
import argparse
import logging
import signal
import json
import serial


def sigterm_handler(_signo, _stack_frame):
    """Raises SystemExit(0)"""
    sys.exit(0)


class ConfigError(Exception):
    """Configuration error exception"""


class Connection():
    """Connection"""
    def __init__(self, connection, ser, log=None):
        self._log = log if log else logging.Logger(self.__class__.__name__)
        self._socket, self._addr = connection
        self._serial = ser

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


class ConnectionTcp(Connection):
    """TCP connection"""
    def __init__(self, connection, ser, log=None):
        super().__init__(connection, ser, log)
        self._log.info("Client connected: %s:%d TCP", *self._addr)

    def send(self, data):
        """Send data to client"""
        if data:
            self._socket.send(data)

    @staticmethod
    def list_pull_first(data):
        """get first entry from array"""
        dat = data[0]
        del data[0]
        return dat

    def on_received(self, data):
        """Received data from client"""
        if data:
            self._serial.send(data)


class ConnectionTelnet(Connection):
    """Telnet connection"""

    # RFC 854 : https://datatracker.ietf.org/doc/html/rfc854.html
    TELNET_SE = 0xf0  # End of subnegotiation parameters.
    TELNET_NOP = 0xf1  # No operation.
    TELNET_DATA_MARK = 0xf2  # The data stream portion of a Synchronization This should always be accompanied by a TCP Urgent notification.
    TELNET_BREAK = 0xf3  # NVT character BRK.
    TELNET_INTERRUPT_PROCESS = 0xf4  # The function IP.
    TELNET_ABORT_OUTPUT = 0xf5  # The function AO.
    TELNET_ARE_YOU_THERE = 0xf6  # The function AYT.
    TELNET_ERASE_CHARACTER = 0xf7  # The function EC.
    TELNET_ERASE_LINE = 0xf8  # The function EL.
    TELNET_GO_AHEAD = 0xf9  # The GA signal.
    TELNET_SB = 0xfa  # Indicates that what follows is subnegotiation of the indicated option.
    TELNET_WILL = 0xfb  # Indicates the desire to begin performing, or confirmation that you are now performing, the indicated option.
    TELNET_WONT = 0xfc  # Indicates the refusal to perform, or continue performing, the indicated option.
    TELNET_DO = 0xfd  # Indicates the request that the other party perform, or confirmation that you are expecting the other party to perform, the indicated option.
    TELNET_DONT = 0xfe  # Indicates the demand that the other party stop performing, or confirmation that you are no longer expecting the other party to perform, the indicated option.
    TELNET_IAC = 0xff  # Data Byte 255.

    TELNET_OPTION_CODES = {
        TELNET_WILL: 'WILL',
        TELNET_WONT: 'WONT',
        TELNET_DO: 'DO',
        TELNET_DONT: 'DONT',
    }

    def __init__(self, connection, ser, log=None):
        super().__init__(connection, ser, log)
        # self._socket.send(b'\xff\xfd\x22')
        # self._socket.send(b'\xff\xfb\x01')
        self._socket.send(bytes((self.TELNET_IAC, self.TELNET_DO, 0x22)))
        self._socket.send(bytes((self.TELNET_IAC, self.TELNET_WILL, 0x01)))
        self._telnet_iac = False
        self._telnet_state = None
        self._subnegotiation_frame = None
        self._log.info("Client connected: %s:%d TELNET", *self._addr)

    def send(self, data):
        """Send data to client"""
        self._socket.send(data.replace(b'\xff', b'\xff\xff'))

    def _telnet_subnegotiation(self, subnegotiation):
        """Process subnegotiation frame"""
        self._log.debug(
            "(%s:%d) received TELNET SUBNEGOTIATION: %s",
            *self._addr, ' '.join(['%02x' % i for i in subnegotiation]))

    def _telnet_command(self, command, value):
        """Process telnet command"""
        self._log.debug(
            "(%s:%d) received TELNET COMMAND: %s 0x%02x",
            *self._addr, self.TELNET_OPTION_CODES[command], value)

    def _send_data(self, data):
        if self._telnet_state is None:
            self._serial.send(data)
        elif self._telnet_state == self.TELNET_SB:
            self._subnegotiation_frame.extend(data)

    def _process_iac(self, state):
        if state in self.TELNET_OPTION_CODES:
            self._telnet_state = state
        elif state == self.TELNET_SB:
            self._telnet_state = state
            self._subnegotiation_frame = bytearray()
        elif state == self.TELNET_SE:
            self._telnet_subnegotiation(self._subnegotiation_frame)
            self._subnegotiation_frame = None
            state = None
        elif state == self.TELNET_IAC:
            self._send_data(bytes((state, )))
        else:
            self._log.warning(
                "(%s:%d) received unexpected TELNET COMMAND: 0x%02x",
                *self._addr, state)

    def on_received(self, data):
        """Received data from client"""
        data = bytearray(data)
        while data:
            if self._telnet_iac:
                # IAC byte was received
                self._telnet_iac = False
                self._process_iac(data.pop(0))
                continue
            if self._telnet_state in self.TELNET_OPTION_CODES:
                self._telnet_command(self._telnet_state, data.pop(0))
                self._telnet_state = None
                continue
            # NO state
            if self.TELNET_IAC in data:
                # find index of IAC
                index = data.index(self.TELNET_IAC)
                if index > 0:
                    # send data before IAC
                    self._send_data(data[:index])
                # remove data + IAC
                del data[:index + 1]
                self._telnet_iac = True
            else:
                self._send_data(data)
                break


class Server():
    """Server connection manager"""

    CONNECTIONS = {
        'TCP': ConnectionTcp,
        'TELNET': ConnectionTelnet,
    }

    def __init__(self, config, ser, log=None):
        self._log = log if log else logging.Logger(self.__class__.__name__)
        self._config = config
        self._serial = ser
        self._connections = []
        self._protocol = self._config['protocol'].upper()
        self._socket = None
        self._log.info(
            "  Server: %s %d %s",
            self._config['address'],
            self._config['port'],
            self._protocol)
        if self._protocol not in self.CONNECTIONS:
            raise ConfigError('Unknown protocol %s' % self._protocol)
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind((config['address'], config['port']))
        self._socket.listen(1)

    def __del__(self):
        self.close()

    def _client_connect(self):
        """connect to client, will accept waiting connection"""
        sock, addr = self._socket.accept()
        if not self._connections and not serial:
            if not self._serial.connect():
                self._log.info("Client canceled: %s:%d", *addr)
                sock.close()
                return
        connection = self.CONNECTIONS[self._protocol](
            connection=(sock, addr),
            ser=self._serial,
            log=self._log,
        )
        if self._serial.connect():
            self._connections.append(connection)
        else:
            connection.close()

    def close_connections(self):
        """close all clients"""
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
                data = con.socket().recv(4096)
                self._log.debug("(%s:%d): %s", *con.get_address(), data)
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


class Serial():
    """Serial connection manager"""
    PARITY_CONFIG = {
        'NONE': serial.PARITY_NONE,
        'EVEN': serial.PARITY_EVEN,
        'ODD': serial.PARITY_ODD,
        'MARK': serial.PARITY_MARK,
        'SPACE': serial.PARITY_SPACE,
    }
    STOPBITS_CONFIG = {
        'ONE': serial.STOPBITS_ONE,
        'ONE_POINT_FIVE': serial.STOPBITS_ONE_POINT_FIVE,
        'TWO': serial.STOPBITS_TWO,
    }
    BYTESIZE_CONFIG = {
        'FIVEBITS': serial.FIVEBITS,
        'SIXBITS': serial.SIXBITS,
        'SEVENBITS': serial.SEVENBITS,
        'EIGHTBITS': serial.EIGHTBITS,
    }

    def __init__(self, config, log=None):
        self._log = log if log else logging.Logger(self.__class__.__name__)
        self._serial = None
        self._servers = []
        self._serial_config = self.fix_serial_config(config['serial'])
        self._log.info(
            "Serial: %s %d",
            self._serial_config['port'],
            self._serial_config['baudrate'])
        for server_config in config['servers']:
            self._servers.append(Server(server_config, self, log))

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
                self._serial = serial.Serial(**self._serial_config)
            except (serial.SerialException, OSError) as err:
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
            except serial.SerialException:
                for server in self._servers:
                    server.close_connections()
                self.disconnect()
                return

    def send(self, data):
        """Send data to serial port"""
        if self._serial:
            self._serial.write(data)


class ServersManager():
    """Servers manager"""
    def __init__(self):
        self._servers = []

    def add_server(self, server):
        """Add server"""
        self._servers.append(server)

    def process(self):
        """Process all servers"""
        sockets = []
        for server in self._servers:
            sockets.extend(server.sockets())
        read_sockets = select.select(sockets, [], [], .1)[0]
        if read_sockets:
            for server in self._servers:
                server.socket_event(read_sockets)

    def close(self):
        """Close all servers"""
        for server in self._servers:
            server.close()


VERSION_STR = "ser2tcp v3.0"

DESCRIPTION_STR = VERSION_STR + """
(c) 2016-2021 by pavel.revak@gmail.com
https://github.com/pavelrevak/ser2tcp
"""


def main():
    """Main"""
    signal.signal(signal.SIGTERM, sigterm_handler)
    signal.signal(signal.SIGINT, sigterm_handler)
    parser = argparse.ArgumentParser(description=DESCRIPTION_STR)
    parser.add_argument('-V', '--version', action='version', version=VERSION_STR)
    parser.add_argument(
        '-v', '--verbose', action='count', default=0,
        help="Increase verbosity")
    parser.add_argument(
        '-c', '--config', required=True,
        help="configuration in json format")
    args = parser.parse_args()

    logging.basicConfig(format='%(asctime)-15s %(levelname)s : %(message)s')
    log = logging.getLogger('ser2tcp')
    log.setLevel((30, 20, 10)[min(2, args.verbose)])

    # check version of python
    if sys.version_info < (3, 5):
        log.error("Wrong python version, required is at lease 3.5")
        sys.exit(1)
    # check pyserial version
    if serial.__version__ < '3.0':
        log.error("Wrong pyserial version, required is at lease 3.0")
        sys.exit(1)

    configuration = []
    with open(args.config, "r", encoding='utf-8') as config_file:
        configuration = json.load(config_file)

    servers_manager = ServersManager()
    try:
        for config in configuration:
            servers_manager.add_server(Serial(config, log))
        while True:
            servers_manager.process()
    except OSError as err:
        log.info(err)
    finally:
        log.info("Exiting..")
        servers_manager.close()


if __name__ == '__main__':
    main()
