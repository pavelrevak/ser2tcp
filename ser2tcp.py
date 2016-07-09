"""Ser2tcp
Simple proxy for connecting over TCP or telnet to serial port
"""

import select
import socket
import argparse
import logging
import serial


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
        self._log.info("Client connected: %s:%d", self._addr[0], self._addr[1])

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
            self._log.info("Client disconnected: %s:%d", self._addr[0], self._addr[1])

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

    @staticmethod
    def filter_telnet_commands(data):
        """Remove telnet commands from data"""

        out = []
        subnegotiation = False
        sbn = []

        # process telnet commands
        while data:
            dat = Ser2TcpConnection.list_pull_first(data)
            if dat == 255:
                dat = Ser2TcpConnection.list_pull_first(data)
                if dat in (251, 252, 253, 254):
                    dat = Ser2TcpConnection.list_pull_first(data)
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
            data = Ser2TcpConnection.filter_telnet_commands(data)
        if data:
            self._serial.write(data)


class Ser2TcpServer():
    """Telnet server"""

    def __init__(self, bind_address, serial_params, telnet=False, log=None):
        """Ser2TcpServer start ser2Tcp server
        Arguments:
            bind_address: ip_address and port to bind (address:port), default: 127.0.0.1:10000
            serial_params: ip_address and port to bind (address:port), default: 127.0.0.1:10000
            telnet: if true use telnet mode for clients, instead raw TCP connection is used
            log: logging.Logger instance for logging
        """
        self._log = log if log else logging.Logger("Ser2TcpServer")
        self._log.info(
            "Starting server (listen: %s, serial: %s:%d)..",
            bind_address, serial_params['port'], serial_params['baud'])

        address, port = bind_address.split(':')
        if not address:
            address = '127.0.0.1'
        port = int(port) if port else 10000
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind((address, port))
        self._socket.listen(1)
        self._connections = []
        self._serial = None
        self._serial_params = serial_params
        parity = serial.PARITY_NONE
        stopbits = serial.STOPBITS_ONE
        if 'EVEN' in serial_params['flags']:
            parity = serial.PARITY_EVEN
        elif 'ODD' in serial_params['flags']:
            parity = serial.PARITY_ODD
        if 'TWO' in serial_params['flags']:
            stopbits = serial.STOPBITS_TWO
        self._serial_params['parity'] = parity
        self._serial_params['stopbits'] = stopbits
        self._telnet = telnet

    def __del__(self):
        self.close()

    def _serial_connect(self):
        if self._serial:
            return True
        try:
            self._serial = serial.Serial(
                port=self._serial_params['port'],
                baudrate=self._serial_params['baud'],
                parity=self._serial_params['parity'],
                stopbits=self._serial_params['stopbits'],
            )
        except (serial.SerialException, OSError) as err:
            self._log.warning("Serial %s is not connected %s", self._serial_params['port'], err)
            return False
        self._log.info("Serial %s connected", self._serial_params['port'])
        return True

    def _serial_disconnect(self):
        if self._serial:
            self._serial.close()
            self._serial = None
            self._log.info("Serial %s disconnected", self._serial_params['port'])

    def _client_connect(self):
        sock, addr = self._socket.accept()
        if not self._connections and not self._serial:
            if not self._serial_connect():
                self._log.info("Client canceled: %s:%d", socket, addr)
                sock.close()
                return
        ser2tcp_connection = Ser2TcpConnection(
            connection=(sock, addr),
            ser=self._serial,
            telnet=self._telnet,
            log=self._log,
        )
        self._connections.append(ser2tcp_connection)

    def _clients_disconnect(self):
        for con in self._connections:
            con.close()
        self._connections = []

    def close(self):
        """Close socket and all connections"""
        self._log.info("Exiting..")
        self._clients_disconnect()
        self._serial_disconnect()
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def process(self):
        """Task start"""
        sockets = [self._socket] + self._connections
        if self._serial:
            sockets.append(self._serial)
        read_sockets = select.select(sockets, [], [], .1)[0]
        if not read_sockets:
            return
        if self._socket in read_sockets:
            self._client_connect()
            return
        raw_data = None
        if self._serial in read_sockets:
            try:
                raw_data = self._serial.read()
            except serial.SerialException:
                self._clients_disconnect()
                self._serial_disconnect()
                return
        for con in self._connections:
            if con in read_sockets:
                data = con.socket.recv(4096)
                if not data:
                    con.close()
                    self._connections.remove(con)
                    if not self._connections:
                        self._serial_disconnect()
                    return
                con.on_received(data)
            if raw_data:
                con.send(raw_data)


VERSION_STR = "ser2tcp v1.0.0"

DESCRIPTION_STR = VERSION_STR + """
(c) 2016 by pavel.revak@gmail.com
https://github.com/pavelrevak/ser2tcp
"""

def main():
    """Main"""
    parser = argparse.ArgumentParser(description=DESCRIPTION_STR)
    parser.add_argument('-V', '--version', action='version', version=VERSION_STR)
    parser.add_argument(
        '-v', '--verbose', action='count', default=0,
        help="Increase verbosity *")
    parser.add_argument(
        '-t', '--telnet', action='store_true', default=0,
        help="telnet (use telnet protocol)")
    parser.add_argument(
        '-l', '--listen', default='127.0.0.1:10000',
        help="Listen host (default: 127.0.0.1:10000)")
    parser.add_argument(
        'port',
        help="Serial port")
    parser.add_argument(
        'baud', type=int,
        help="Serial baud rate")
    parser.add_argument(
        'flags', nargs='*', choices=['NONE', 'EVEN', 'ODD', 'ONE', 'TWO'],
        help="Serial parameters: parity: [NONE|EVEN|ODD], stop bits: [ONE|TWO], default: NONE ONE")
    args = parser.parse_args()

    logging.basicConfig(format='%(asctime)-15s %(message)s')
    log = logging.getLogger('ser2tcp')
    if args.verbose:
        log.setLevel(10)

    ser2tcp = Ser2TcpServer(
        bind_address=args.listen,
        serial_params={
            'port': args.port,
            'baud': args.baud,
            'flags': args.flags,
        },
        telnet=args.telnet,
        log=log,
    )
    try:
        while True:
            ser2tcp.process()
    except Exception as err:
        print("%s" % err)
        raise err
    except KeyboardInterrupt:
        pass
    finally:
        ser2tcp.close()


if __name__ == '__main__':

    main()
