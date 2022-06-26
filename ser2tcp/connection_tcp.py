"""Connection Telnet"""
from __future__ import annotations

import logging as _logging
from typing import Tuple

import ser2tcp.serial_proxy as _serial_proxy
import ser2tcp.connection as _connection


class ConnectionTcp(_connection.Connection):
    """TCP connection"""
    
    def __init__(
            self,
            connection: Tuple[str, int],
            ser: _serial_proxy.SerialProxy,
            log_global: _logging.Logger,
            log_serial: _logging.Logger
        ):
        super().__init__(connection, log_global, log_serial)
        self._serial = ser
        ip, port = self._addr
        self._log_global.info(f"Client connected: {ip}:{port} TCP")

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
