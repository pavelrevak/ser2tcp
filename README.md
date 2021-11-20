# Ser2tcp
Simple proxy for connecting over TCP or telnet to serial port

## Features
- Serial:
  - port
  - baudrate
  - parity (NONE, EVEN, ODD)
  - stopbits (ONE, TWO)
- TCP:
  - allow to set listening socket (address and port, default: localhost:10000, change with: ```-l``` or ```--listen``` param)
  - telnet mode (send every character immediately and not waiting to enter, with ```-t``` or ```--telnet``` param)
  - allow multiple connections to one serial port:
    - each connected client can sent to serial
    - serial send received data to all connected clients

## Usage examples:
```
python ser2tcp.py localhost 10001 /dev/ttyS0 9600
python ser2tcp.py 0 12345 telnet /dev/tty.SLAB_USBtoUART 115200 EVEN ONE
python ser2tcp.py 0 10001 COM1 115200 ODD TWO
python ser2tcp.py --help                                              
```

## Requirements
- python v3.5+
- pyserial v3.0+

### Running on:
- Linux
- MacOS
- Windows
