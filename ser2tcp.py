"""Ser2tcp
Simple proxy for connecting over TCP or telnet to serial port
"""

import sys
import select
import socket
import argparse
import logging
import signal
import serial


def sigterm_handler(_signo, _stack_frame):
    """Raises SystemExit(0)"""
    sys.exit(0)


class ConfigError(Exception):
    """Configuration error exception"""


class Ser2TcpConnection():
    """Telnet socket"""
    def __init__(self, connection, ser, telnet=False, log=None):
        self._socket, self._addr = connection
        self._serial = ser
        self._telnet = telnet
        self._log = log if log else logging.Logger("Ser2TcpConnection")
        if self._telnet:
            self.send((0xff, 0xfd, 0x22))
            self.send((0xff, 0xfb, 0x01))
        self._log.info(
            "Client connected: %s:%d%s",
            *self._addr, " TELNET" if self._telnet else "")

    def __del__(self):
        self.close()

    @property
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

    def send(self, data):
        """Send data to client"""
        raw_data = []
        for dat in data:
            if not self._telnet and dat == 255:
                raw_data.append(255)
            raw_data.append(dat)
        self._socket.send(bytearray(data))

    @staticmethod
    def list_pull_first(data):
        """get first entry from array"""
        dat = data[0]
        del data[0]
        return dat

    @classmethod
    def filter_telnet_commands(cls, data):
        """Remove telnet commands from data"""
        out = []
        subnegotiation = False
        sbn = []

        # process telnet commands
        while data:
            dat = cls.list_pull_first(data)
            if dat == 255:
                dat = cls.list_pull_first(data)
                if dat in (251, 252, 253, 254):
                    dat = cls.list_pull_first(data)
                    continue
                if dat == 250:
                    subnegotiation = True
                    continue
                if dat == 240:
                    subnegotiation = False
                    continue
            if subnegotiation:
                sbn.append(dat)
                continue
            if dat == 13:
                out.append(10)
            out.append(dat)

        return out

    def on_received(self, data):
        """Received data from client"""
        data = list(data)
        if self._telnet:
            data = self.filter_telnet_commands(data)
        if data:
            self._serial.write(data)

    def get_address(self):
        """Return address"""
        return self._addr


class Ser2TcpServer():
    """Telnet server"""
    def __init__(self, config, log=None):
        """Ser2TcpServer start ser2Tcp server"""
        self._log = log if log else logging.Logger("Ser2TcpServer")
        self._log.info("Starting server (%s)..", config)
        self._config = config
        self._connections = []
        self._serial = None
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind(config.get_bind_address())
        self._socket.listen(1)

    def __del__(self):
        self.close()

    def _serial_connect(self):
        if self._serial:
            return True
        try:
            self._serial = serial.Serial(**self._config.get_serial_config())
        except (serial.SerialException, OSError) as err:
            self._log.warning(
                "Serial %s is not connected [%s]",
                self._config.get_serial_port(), err)
            return False
        self._log.info(
            "Serial %s connected", self._config.get_serial_port())
        return True

    def _serial_disconnect(self):
        if self._serial:
            self._serial.close()
            self._serial = None
            self._log.info(
                "Serial %s disconnected", self._config.get_serial_port())

    def _client_connect(self):
        sock, addr = self._socket.accept()
        if not self._connections and not self._serial:
            if not self._serial_connect():
                self._log.info("Client canceled: %s:%d", *addr)
                sock.close()
                return
        ser2tcp_connection = Ser2TcpConnection(
            connection=(sock, addr),
            ser=self._serial,
            telnet=self._config.is_telnet(),
            log=self._log,
        )
        self._connections.append(ser2tcp_connection)

    def _clients_disconnect(self):
        while self._connections:
            self._connections.pop().close()

    def close(self):
        """Close socket and all connections"""
        self._clients_disconnect()
        self._serial_disconnect()
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def sockets(self):
        """Return all sockets from this server"""
        sockets = [self._socket] + self._connections
        if self._serial:
            sockets.append(self._serial)
        return sockets

    def socket_event(self, read_sockets):
        """Process sockets with read event"""
        if self._socket in read_sockets:
            self._client_connect()
            return
        serial_data = None
        if self._serial and self._serial in read_sockets:
            try:
                serial_data = self._serial.read()
                self._log.debug("(%s): %s", self._config.get_serial_port(), serial_data)
            except serial.SerialException:
                self._clients_disconnect()
                self._serial_disconnect()
                return
        for con in self._connections:
            if con in read_sockets:
                con_data = con.socket.recv(4096)
                self._log.debug("(%s:%d): %s", *con.get_address(), con_data)
                if not con_data:
                    con.close()
                    self._connections.remove(con)
                    if not self._connections:
                        self._serial_disconnect()
                    return
                con.on_received(con_data)
            if serial_data:
                con.send(serial_data)


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


class Config():
    """Configuration"""
    def __init__(self, entry):
        if not entry:
            raise ConfigError("Empty configuration")
        self._host = entry.pop(0)
        if not entry:
            raise ConfigError("Missing port")
        if not entry[0].isnumeric():
            raise ConfigError("Wrong port number")
        self._port = int(entry.pop(0))
        if not entry:
            raise ConfigError("Missing serial port")
        self._mode = 'RAW'
        if entry[0].upper() in ('RAW', 'TELNET'):
            self._mode = entry.pop(0).upper()
        if not entry:
            raise ConfigError("Missing serial port")
        self._serial_port = entry.pop(0)
        if not entry:
            raise ConfigError("Missing baud-rate")
        if not entry[0].isnumeric():
            raise ConfigError("Wrong baud-rate")
        self._baud_rate = int(entry.pop(0))
        self._parity = 'NONE'
        if entry and entry[0].upper() in ('NONE', 'EVEN', 'ODD'):
            self._parity = entry.pop(0)
        self._stop_bits = 'ONE'
        if entry and entry[0].upper() in ('ONE', 'TWO'):
            self._stop_bits = entry.pop(0)
        if entry:
            raise ConfigError("Too many parameters")

    def __str__(self):
        return ' '.join((
            self._host + ":" + str(self._port),
            self._mode,
            self._serial_port,
            str(self._baud_rate),
            self._parity,
            self._stop_bits))

    def get_bind_address(self):
        """Return bind address for TCP server"""
        return (self._host, self._port)

    def is_telnet(self):
        """Return True if connection emulates telnet server"""
        return self._mode == 'TELNET'

    def get_serial_config(self):
        """Return configuration parameters for serial"""
        parity = serial.PARITY_NONE
        stop_bits = serial.STOPBITS_ONE
        if 'EVEN' in self._parity:
            parity = serial.PARITY_EVEN
        elif 'ODD' in self._parity:
            parity = serial.PARITY_ODD
        if 'TWO' in self._stop_bits:
            stop_bits = serial.STOPBITS_TWO
        return {
            'port': self._serial_port,
            'baudrate': self._baud_rate,
            'parity': parity,
            'stopbits': stop_bits,
        }

    def get_serial_port(self):
        """Return serial port """
        return self._serial_port


VERSION_STR = "ser2tcp v2.0.0"

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
        help="Increase verbosity *")
    parser.add_argument(
        'connection', nargs=argparse.REMAINDER,
        help="{host} {port} [RAW|TELNET]"
        " {serial_port} {baud_rate} [NONE|EVEN|ODD] [ONE|TWO]")
    args = parser.parse_args()

    logging.basicConfig(format='%(asctime)-15s %(levelname)s : %(message)s')
    log = logging.getLogger('ser2tcp')
    verbose_level = min(2, args.verbose)
    log.setLevel((30, 20, 10)[verbose_level])

    # check version of python
    if sys.version_info < (3, 6):
        log.error("Wrong python version, required is at lease 3.5")
        sys.exit(1)
    # check pyserial version
    pyserial_version = [int(i) for i in serial.__version__.split('.')]
    if pyserial_version[0] < 3:
        log.error("Wrong pyserial version, required is at lease 3.0")
        sys.exit(1)

    connections = []
    try:
        if args.connection:
            connections.append(Config(args.connection))
        if not connections:
            raise ConfigError("No connection configured")
    except ConfigError as err:
        log.error(err)
        sys.exit(0)

    servers_manager = ServersManager()
    try:
        for config in connections:
            servers_manager.add_server(Ser2TcpServer(config, log))
        while True:
            servers_manager.process()
    except OSError as err:
        log.info(err)
    finally:
        log.info("Exiting..")
        servers_manager.close()


if __name__ == '__main__':
    main()
