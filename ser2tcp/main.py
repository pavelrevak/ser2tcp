"""Ser2tcp
Simple proxy for connecting over TCP or telnet to serial port
"""

import argparse as _argparse
import importlib.metadata as _metadata
import json as _json
import logging as _logging
import signal as _signal

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
https://github.com/pavelrevak/ser2tcp
"""


def main():
    """Main"""
    parser = _argparse.ArgumentParser(description=DESCRIPTION_STR)
    parser.add_argument('-V', '--version', action='version', version=VERSION_STR)
    parser.add_argument(
        '-v', '--verbose', action='count', default=0,
        help="Increase verbosity")
    parser.add_argument(
        '-c', '--config', required=True,
        help="configuration in JSON format")
    args = parser.parse_args()

    _logging.basicConfig(format='%(levelname).1s: %(message)s (%(filename)s:%(lineno)s)')
    log = _logging.getLogger('ser2tcp')
    log.setLevel((30, 20, 10)[min(2, args.verbose)])

    configuration = []
    with open(args.config, "r", encoding='utf-8') as config_file:
        configuration = _json.load(config_file)

    servers_manager = _server_manager.ServersManager()
    for config in configuration:
        servers_manager.add_server(_serial_proxy.SerialProxy(config, log))

    _signal.signal(_signal.SIGTERM, servers_manager.stop)
    _signal.signal(_signal.SIGINT, servers_manager.stop)

    servers_manager.run()
    log.info("Exiting..")
