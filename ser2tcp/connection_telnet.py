"""Connection Telnet"""
from __future__ import annotations

import logging as _logging
from typing import Tuple

import ser2tcp.connection as _connection
import ser2tcp.serial_proxy as _serial_proxy
import ser2tcp.connection as _connection


class ConnectionTelnet(_connection.Connection):
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

    def __init__(
            self,
            connection: Tuple[str, int],
            ser: _serial_proxy.SerialProxy,
            log_global: _logging.Logger,
            log_serial: _logging.Logger
        ):
        super().__init__(connection, log_global, log_serial)
        self._serial = ser
        self._socket.sendall(bytes((self.TELNET_IAC, self.TELNET_DO, 0x22)))
        self._socket.sendall(bytes((self.TELNET_IAC, self.TELNET_WILL, 0x01)))
        self._telnet_iac = False
        self._telnet_state = None
        self._subnegotiation_frame = None
        ip, port = self._addr
        self._log_global.info(f"Client connected: {ip}:{port} TELNET")
        self._log_serial.info(f"Client connected: {ip}:{port} TELNET")

    def send(self, data):
        """Send data to client"""
        super().send(data.replace(b'\xff', b'\xff\xff'))

    def _telnet_subnegotiation(self, subnegotiation):
        """Process subnegotiation frame"""
        message = "({}:{}) received TELNET SUBNEGOTIATION: {}".format(
            *self._addr,
            ' '.join([f'{i:02x}' for i in subnegotiation])
        )
        self._log_global.debug(message)
        self._log_serial.debug(message)
        

    def _telnet_command(self, command, value):
        """Process telnet command"""
        message = "({}:{}) received TELNET COMMAND: {} {:02x}".format(
            *self._addr,
            self.TELNET_OPTION_CODES[command],
            value
        )
        self._log_global.debug(message)
        self._log_serial.debug(message)


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
            message = "({}:{}) received unexpected TELNET COMMAND: {:02x}".format(
                *self._addr,
                state
            )
            self._log_global.warning(message)
            self._log_serial.warning(message)


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
