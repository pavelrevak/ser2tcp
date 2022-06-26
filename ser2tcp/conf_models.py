import serial as _serial
import logging as _logging
from logging import config as _logging_config
from typing import Literal, Optional, List
from pydantic import BaseModel, validator

import ser2tcp.connection_tcp as _connection_tcp
import ser2tcp.connection_telnet as _connection_telnet


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
CONNECTIONS = {
    'TCP': _connection_tcp.ConnectionTcp,
    'TELNET': _connection_telnet.ConnectionTelnet,
}


class SerialInstance(BaseModel):
    port: str
    baudrate: int = 115200
    parity: Literal['NONE', 'EVEN', 'ODD', 'MARK', 'SPACE'] = 'NONE'
    stopbits: Literal['ONE', 'ONE_POINT_FIVE', 'TWO'] = 'ONE'
    bytesize: Literal['FIVEBITS', 'SIXBITS', 'SEVENBITS', 'EIGHTBITS'] = 'EIGHTBITS'
    timeout: Optional[float] = None
    xonxoff: bool = False
    rtscts: bool = False
    dsrdtr: bool = False
    write_timeout: Optional[float] = None
    inter_byte_timeout: Optional[float] = None

    @validator('parity', always=True)
    def val_parity(cls, v):
        if v in PARITY_CONFIG:
            return PARITY_CONFIG[v]

    @validator('stopbits', always=True)
    def val_stopbits(cls, v):
        if v in STOPBITS_CONFIG:
            return STOPBITS_CONFIG[v]

    @validator('bytesize', always=True)
    def val_bytesize(cls, v):
        if v in BYTESIZE_CONFIG:
            return BYTESIZE_CONFIG[v]

class ServerInstance(BaseModel):
    port: int
    address: str = '0.0.0.0'
    protocol: Literal['TELNET', 'TCP']

    @validator('protocol', always=True)
    def val_protocol(cls, v):
        p = v.upper()
        if p in CONNECTIONS:
            return CONNECTIONS[p]

class SerialMappingInstance(BaseModel):
    serial: SerialInstance
    servers: List[ServerInstance]
    logger_config: Optional[dict]
    logger: Optional[object] = None

    def create_loggers(self):
        if self.logger_config:
            _logging_config.dictConfig(self.logger_config)
            self.logger = _logging.getLogger(self.serial.port)
        else:
            # create a disabled logger 
            _logging.basicConfig(format='%(levelname).1s: %(message)s (%(filename)s:%(lineno)s)')
            self.logger = _logging.getLogger(self.serial.port)
            self.logger.setLevel(_logging.DEBUG)
            self.logger.disabled = True

class SerialConfig(BaseModel):
    __root__: List[SerialMappingInstance]