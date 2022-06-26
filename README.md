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
- parsing of the json config files via pydantic
- Flexible logging via the python logging module [configuration](https://docs.python.org/3/library/logging.config.html#configuration-dictionary-schema)
    - either on a per port serial config
    - or a global configuration

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
$ ser2tcp -h
usage: ser2tcp [-h] [-V] [-v] [-d] -c CONFIG [-g GLOBAL_LOG_CONFIG]

ser2tcp v3.0 (c) 2016-2021 by pavel.revak@gmail.com https://github.com/pavelrevak/ser2tcp

optional arguments:
  -h, --help            show this help message and exit
  -V, --version         show program's version number and exit
  -v, --verbose         Increase verbosity: warning (default), info (-v), debug (-vv)
  -d, --no_logger       Disable the default logger to stdout
  -c CONFIG, --config CONFIG
                        configuration in JSON format
  -g GLOBAL_LOG_CONFIG, --global_log_config GLOBAL_LOG_CONFIG
                        global logging configuration in JSON format
```

### Verbose
- By default print only ERROR and WARNING messages
- `-v`: will print INFO messages
- `-vv`: print also DEBUG messages

## Configuration

The configuration is a json list, each list item containing:
- `serial`: dictionary describing the parameters needed to open the serial connection.
  - port: name of the device to connect to.
  - baudrate (optional, default: 115200) any valid serial speed that pySerial accepts
  - parity (optional, default: 'NONE') one of['ONE', 'ONE_POINT_FIVE', 'TWO']
  - bytesize (optional, default: 'EIGHTBITS') one of['FIVEBITS', 'SIXBITS', 'SEVENBITS', 'EIGHTBITS']
  - timeout (optional, default None, keep waiting forever)
  - xonxoff (optional, default: False)
  - rtscts (optional, default: False)
  - dsrdtr (optional, default: False)
  - write_timeout (optional, default: None)
  - inter_byte_timeout (optional, default: None)
- `servers`: dictionary describing the parameters needed to open the listening interfaces for external connections
  - port: any valid port number
  - address: listening address (optional, default: '0.0.0.0')
  - protocol: on of ['TELNET', 'TCP']
- `logger_config` (optional): define the logging options you need from the python logging module. Format and options can be found at: [handlers](https://docs.python.org/3/library/logging.handlers.html)

### Configuration file example (no logging, global or port based)
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

### Configuration file example (port based logging)
```json
[
    {
        "serial": {
            "port": "/dev/ttyUSB0",
            "baudrate": 115200,
            "parity": "NONE",
            "stopbits": "ONE"
        },
        "servers": [
            {
                "address": "0.0.0.0",
                "port": 10001,
                "protocol": "TCP"
            },
            {
                "address": "0.0.0.0",
                "port": 10002,
                "protocol": "TELNET"
            }
        ],
        "logger_config": {
            "version": 1,
            "disable_existing_loggers": false,
            "formatters": {
                "log_format": {
                    "format": "MC [ %(asctime)s ] %(levelname).1s: %(message)s (%(filename)s:%(lineno)s)"
                }
            },

            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "level": "DEBUG",
                    "formatter": "log_format",
                    "stream": "ext://sys.stdout"
                },

                "file_handler": {
                    "class": "logging.FileHandler",
                    "level": "DEBUG",
                    "formatter": "log_format",
                    "filename": "serial.log"
                },

                "syslog_handler": {
                    "class": "logging.handlers.SysLogHandler",
                    "level": "DEBUG",
                    "formatter": "log_format",
                    "address": ["localhost", 514]
                }
            },

            "loggers": {
                "/dev/ttyUSB0": {
                    "level": "DEBUG",
                    "handlers": ["console", "file_handler", "syslog_handler"]
                }
            }
        }
    }
]
```

**note**: the logger name defined in the "loggers" section needs to match the "serial" "port" name, otherwise the main program can't find the configuration when it tries to load it.

### Configuration file example (global logging)

```json
{
    "version": 1,
    "disable_existing_loggers": false,
    "formatters": {
        "log_format": {
            "format": "GC [ %(asctime)s ] %(levelname).1s: %(message)s (%(filename)s:%(lineno)s)"
        }
    },

    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "DEBUG",
            "formatter": "log_format",
            "stream": "ext://sys.stdout"
        },

        "file_handler": {
            "class": "logging.FileHandler",
            "level": "DEBUG",
            "formatter": "log_format",
            "filename": "global.log"
        },

        "syslog_handler": {
            "class": "logging.handlers.SysLogHandler",
            "level": "DEBUG",
            "formatter": "log_format",
            "address": ["localhost", 514]
        }
    },

    "loggers": {
        "ser2tcp": {
            "level": "DEBUG",
            "handlers": ["console", "file_handler", "syslog_handler"]
        }
    }
}
```

**note**: the logger name defined in the "loggers" section needs to be called `ser2tcp`, otherwise the main program can't find the configuration when it tries to load it.

## Usage examples
For installed version:
```
ser2tcp -c ser2tcp.conf
```
Direct running from repository:
```
python3 run.py -c ser2tcp.conf
```
Running with a global config:

**note**: make sure the -c config does not contain logging configuration.
```
ser2tcp -c ser2tcp.conf -g global_logging.conf
```

### Connecting using telnet
```
telnet 0 10012
```
(to exit telnet press `CTRL + ]` and type `quit`)

## Installation as server
### Linux - systemd local user service
1. edit configuration file `~/.config/ser2tcp.conf`
1. reload user systemd services:
    ```
    systemctl --user daemon-reload
    ```
1. start service:
    ```
    systemctl --user start ser2tcp
    ```
1. auto-start service:
    ```
    systemctl --user enable ser2tcp
    ```
1. to allow user services running after boot you need to enable linger as root (if this is not configured, then service will start after user login and stop after logout):
    ```
    sudo loginctl enable-linger $USER
    ```

#### Other useful commands
* check if service is running:
    ```
    systemctl --user status ser2tcp
    ```
* stop service:
    ```
    systemctl --user stop ser2tcp
    ```
* stop restart:
    ```
    systemctl --user restart ser2tcp
    ```
* see logs from service:
    ```
    journalctl --user-unit ser2tcp -e
    ```
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
