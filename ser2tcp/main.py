"""Ser2tcp
Simple proxy for connecting over TCP or telnet to serial port
"""

import argparse as _argparse
import importlib.metadata as _metadata
import json as _json
import logging as _logging
import signal as _signal

import serial.tools.list_ports as _list_ports

import ser2tcp.serial_proxy as _serial_proxy
import ser2tcp.server_manager as _server_manager

try:
    _about = _metadata.metadata("ser2tcp")
    VERSION_STR = "%s %s (%s)" % (
        _about["Name"], _about["Version"], _about["Author-email"])
except _metadata.PackageNotFoundError:
    VERSION_STR = "ser2tcp (not installed)"

DESCRIPTION_STR = VERSION_STR + """
(c) 2016-2026 by pavel.revak@gmail.com
https://github.com/cortexm/ser2tcp
"""


def list_usb_devices():
    """List USB serial devices with match attributes"""
    devices = []
    for port in _list_ports.comports():
        if port.vid is not None:
            devices.append(port)
    if not devices:
        print("No USB serial devices found")
        return
    for port in devices:
        print(f"{port.device}")
        print(f"  vid: 0x{port.vid:04X}")
        print(f"  pid: 0x{port.pid:04X}")
        if port.serial_number:
            print(f"  serial_number: {port.serial_number}")
        if port.manufacturer:
            print(f"  manufacturer: {port.manufacturer}")
        if port.product:
            print(f"  product: {port.product}")
        if port.location:
            print(f"  location: {port.location}")
        print()


def main():
    """Main"""
    parser = _argparse.ArgumentParser(description=DESCRIPTION_STR)
    parser.add_argument('-V', '--version', action='version', version=VERSION_STR)
    parser.add_argument(
        '-v', '--verbose', action='count', default=0,
        help="Increase verbosity")
    parser.add_argument(
        '-u', '--usb', action='store_true',
        help="List USB serial devices and exit")
    parser.add_argument(
        '--hash-password', metavar='PASSWORD',
        help="Hash password for config file and exit")
    parser.add_argument(
        '-c', '--config',
        help="configuration in JSON format")
    args = parser.parse_args()

    if args.hash_password:
        import ser2tcp.http_auth as _http_auth
        print(_http_auth.hash_password(args.hash_password))
        return

    if args.usb:
        list_usb_devices()
        return

    if not args.config:
        parser.error("--config is required")

    _logging.basicConfig(format='%(levelname).1s: %(message)s (%(filename)s:%(lineno)s)')
    log = _logging.getLogger('ser2tcp')
    log.setLevel((30, 20, 10)[min(2, args.verbose)])

    with open(args.config, "r", encoding='utf-8') as config_file:
        configuration = _json.load(config_file)

    if isinstance(configuration, list):
        ports = configuration
    elif isinstance(configuration, dict):
        ports = configuration.get('ports', [])
    else:
        raise SystemExit("Invalid configuration format")

    if not ports:
        raise SystemExit("No ports configured")

    servers_manager = _server_manager.ServersManager()
    serial_proxies = []
    for config in ports:
        try:
            proxy = _serial_proxy.SerialProxy(config, log)
        except Exception as err:
            log.error("Failed to create port: %s", err)
            continue
        serial_proxies.append(proxy)
        servers_manager.add_server(proxy)

    if isinstance(configuration, dict) and 'http' in configuration:
        import ser2tcp.http_server as _http_server
        http_server = _http_server.HttpServerWrapper(
            configuration['http'], serial_proxies, log,
            config_path=args.config, configuration=configuration,
            server_manager=servers_manager)
        servers_manager.add_server(http_server)

    _signal.signal(_signal.SIGTERM, servers_manager.stop)
    _signal.signal(_signal.SIGINT, servers_manager.stop)

    servers_manager.run()
    log.info("Exiting..")
