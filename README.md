# Ser2tcp
Simple proxy for connecting over TCP or telnet to serial port

## Version
**ser2tcp v3.0** https://github.com/pavelrevak/ser2tcp

## Features
- can serve multiple serial ports using pyserial library
- each serial port can have multiple servers
- server can use TCP or TELNET protocol
  - TCP protocol just bridge whole RAW serial stream to TCP
  - TELNET protocol will send every character immediately and not wait for ENTER, it is useful to use standard `telnet` as serial terminal
- servers accepts multiple connections at one time
    - each connected client can sent to serial port
    - serial port send received data to all connected clients

## Instalation
```
pip3 install .
```

### Uninstal
```
pip3 uninstall ser2tcp
```

## command line options
```
  -h, --help            show this help message and exit
  -V, --version         show program's version number and exit
  -v, --verbose         Increase verbosity
  -c CONFIG, --config CONFIG
                        configuration in json format
```

### Verbose
- By default print only ERROR and WARNING messages
- `-v`: will print INFO messages
- `-vv`: print also DEBUG messages

## Configuration file example
```json
[
    {
        "serial": {
            "port": "/dev/tty.usbserial-01BB6216",
            "baudrate": 115200,
            "parity": "NONE",
            "stopbits": "ONE"
        },
        "servers": [
            {
                "address": "127.0.0.1",
                "port": 10001,
                "protocol": "TCP"
            },
            {
                "address": "0.0.0.0",
                "port": 10002,
                "protocol": "TELNET"
            }
        ]
    },
    {
        "serial": {
            "port": "/dev/tty.usbserial-A6005CNx",
            "baudrate": 115200,
            "parity": "NONE",
            "stopbits": "ONE"
        },
        "servers": [
            {
                "address": "0.0.0.0",
                "port": 10011,
                "protocol": "TCP"
            },
            {
                "address": "192.168.1.123",
                "port": 10012,
                "protocol": "TELNET"
            }
        ]
    }
]
```
`serial` structure pass all parameters to [serial.Serial](https://pythonhosted.org/pyserial/pyserial_api.html#classes) constructor from pyserial library,
this allow full control of the serial port

## Usage examples
For installed version:
```
ser2tcp -c ser2tcp.conf
```
Direct running from repository:
```
python3 run.py -c ser2tcp.conf
```

### Connecting using telnet
```
telnet 0 10012
```
(to exit telnet press `CTRL + ]` and type `quit`)


## Requirements
- python v3.5+
- pyserial v3.0+

### Running on:
- Linux
- MacOS
- Windows

## Credits
(c) 2016-2021 by Pavel Revak

### Support
- Basic support is free over GitHub issues.
- Professional support is available over email: [Pavel Revak](mailto:pavel.revak@gmail.com?subject=[GitHub]%20ser2tcp).
