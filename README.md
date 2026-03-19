# Ser2tcp

Simple proxy for connecting over TCP, TELNET or SSL to serial port

https://github.com/cortexm/ser2tcp

## Features

- can serve multiple serial ports using pyserial library
- each serial port can have multiple servers
- server can use TCP, TELNET or SSL protocol
  - TCP protocol just bridge whole RAW serial stream to TCP
  - TELNET protocol will send every character immediately and not wait for ENTER, it is useful to use standard `telnet` as serial terminal
  - SSL protocol provides encrypted TCP connection with optional mutual TLS (mTLS) client certificate verification
- servers accepts multiple connections at one time
  - each connected client can sent to serial port
  - serial port send received data to all connected clients
- non-blocking send with configurable timeout and buffer limit

## Installation

```
pip install ser2tcp
```

or from source:

```
pip install .
```

### Uninstall

```
pip uninstall ser2tcp
```

## Command line options

```
  -h, --help            show this help message and exit
  -V, --version         show program's version number and exit
  -v, --verbose         Increase verbosity
  -u, --usb             List USB serial devices and exit
  -c CONFIG, --config CONFIG
                        configuration in JSON format
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
            "port": "/dev/ttyUSB0",
            "baudrate": 115200,
            "parity": "NONE",
            "stopbits": "ONE"
        },
        "servers": [
            {
                "address": "127.0.0.1",
                "port": 10001,
                "protocol": "tcp"
            },
            {
                "address": "0.0.0.0",
                "port": 10002,
                "protocol": "telnet",
                "send_timeout": 5.0,
                "buffer_limit": 65536
            }
        ]
    }
]
```

### Serial configuration

`serial` structure pass all parameters to [serial.Serial](https://pythonhosted.org/pyserial/pyserial_api.html#classes) constructor from pyserial library, this allows full control of the serial port.

#### USB device matching

Instead of specifying `port` directly, you can use `match` to find device by USB attributes:

```json
{
    "serial": {
        "match": {
            "vid": "0x303A",
            "pid": "0x4001",
            "serial_number": "dcda0c2004bc0000"
        },
        "baudrate": 115200
    }
}
```

Use `ser2tcp --usb` to list available USB devices with their attributes:

```
$ ser2tcp --usb
/dev/cu.usbmodem1101
  vid: 0x303A
  pid: 0x4001
  serial_number: dcda0c2004bc0000
  manufacturer: Espressif Systems
  product: Espressif Device
  location: 1-1
```

Match attributes: `vid`, `pid`, `serial_number`, `manufacturer`, `product`, `location`

- Wildcard `*` supported (e.g. `"product": "CP210*"`)
- Matching is case-insensitive
- Error if multiple devices match the criteria
- Device is resolved when client connects, not at startup (device does not need to exist at startup)
- `baudrate` is optional (default 9600, CDC devices ignore it)

### Server configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `address` | Bind address | required |
| `port` | TCP port | required |
| `protocol` | `tcp`, `telnet` or `ssl` | required |
| `ssl` | SSL configuration (required for `ssl` protocol) | - |
| `send_timeout` | Disconnect client if data cannot be sent within this time (seconds) | 5.0 |
| `buffer_limit` | Maximum send buffer size per client (bytes), `null` for unlimited | null |

#### SSL configuration

For `ssl` protocol, add `ssl` object with certificate paths:

```json
{
    "address": "0.0.0.0",
    "port": 10003,
    "protocol": "ssl",
    "ssl": {
        "certfile": "/path/to/server.crt",
        "keyfile": "/path/to/server.key",
        "ca_certs": "/path/to/ca.crt"
    }
}
```

| Parameter | Description | Required |
|-----------|-------------|----------|
| `certfile` | Server certificate (PEM) | yes |
| `keyfile` | Server private key (PEM) | yes |
| `ca_certs` | CA certificate for client verification (mTLS) | no |

If `ca_certs` is specified, clients must provide a valid certificate signed by the CA.

##### Creating self-signed certificates

Generate CA and server certificate for testing:

```bash
# Create CA key and certificate
openssl genrsa -out ca.key 2048
openssl req -new -x509 -days 365 -key ca.key -out ca.crt -subj "/CN=ser2tcp CA" \
    -addext "basicConstraints=critical,CA:TRUE" \
    -addext "keyUsage=critical,keyCertSign,cRLSign"

# Create server key and certificate signing request
openssl genrsa -out server.key 2048
openssl req -new -key server.key -out server.csr -subj "/CN=localhost"

# Sign server certificate with CA
openssl x509 -req -days 365 -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out server.crt

# For certificate bound to specific domain/IP (SAN - Subject Alternative Name):
openssl req -new -key server.key -out server.csr -subj "/CN=myserver.example.com" -addext "subjectAltName=DNS:myserver.example.com,DNS:localhost,IP:192.168.1.100"
openssl x509 -req -days 365 -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out server.crt -copy_extensions copy

# Clean up CSR
rm server.csr
```

For mTLS (mutual TLS with client certificates):

```bash
# Create client key and certificate
openssl genrsa -out client.key 2048
openssl req -new -key client.key -out client.csr -subj "/CN=client"
openssl x509 -req -days 365 -in client.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out client.crt
rm client.csr
```

Testing SSL connection:

```bash
# Without client certificate
openssl s_client -connect localhost:10003

# With client certificate (mTLS)
openssl s_client -connect localhost:10003 -cert client.crt -key client.key
```

## Usage examples

```
ser2tcp -c ser2tcp.conf
```

Direct running from repository:

```
python run.py -c ser2tcp.conf
```

### Connecting using telnet

```
telnet localhost 10002
```

(to exit telnet press `CTRL + ]` and type `quit`)

## Installation as service

### Linux - systemd user service

1. Copy service file:
    ```
    cp ser2tcp.service ~/.config/systemd/user/
    ```
2. Create configuration file `~/.config/ser2tcp.conf`
3. Reload user systemd services:
    ```
    systemctl --user daemon-reload
    ```
4. Start and enable service:
    ```
    systemctl --user enable --now ser2tcp
    ```
5. To allow user services running after boot you need to enable linger (if this is not configured, then service will start after user login and stop after logout):
    ```
    sudo loginctl enable-linger $USER
    ```

### Linux - systemd system service

1. Create system user:
    ```
    sudo useradd -r -s /usr/sbin/nologin -G dialout ser2tcp
    ```
2. Copy service file:
    ```
    sudo cp ser2tcp-system.service /etc/systemd/system/ser2tcp.service
    ```
3. Create configuration file `/etc/ser2tcp.conf`
4. Reload systemd and start service:
    ```
    sudo systemctl daemon-reload
    sudo systemctl enable --now ser2tcp
    ```

### Useful commands

```bash
# Check status
systemctl --user status ser2tcp

# View logs
journalctl --user-unit ser2tcp -e

# Restart
systemctl --user restart ser2tcp

# Stop
systemctl --user stop ser2tcp
```

For system service, use `sudo systemctl` instead of `systemctl --user`.

## Requirements

- Python 3.8+
- pyserial 3.0+

### Running on

- Linux
- macOS
- Windows

## Credits

(c) 2016-2026 by Pavel Revak

### Support

- Basic support is free over GitHub issues.
- Professional support is available over email: [Pavel Revak](mailto:pavel.revak@gmail.com?subject=[GitHub]%20ser2tcp).
