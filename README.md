# Ser2tcp
Simple proxy for connecting over TCP or telnet to serial port

## Usage examples:
```
python ser2tcp.py /dev/ttyS0 9600
python ser2tcp.py /dev/tty.SLAB_USBtoUART 115200 EVEN -l 0:10001 -t -v
python ser2tcp.py COM1 115200 ODD TWO -l 0:10001 -v
```
