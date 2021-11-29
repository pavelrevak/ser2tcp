"""Ser2tcp
Simple proxy for connecting over TCP or telnet to serial port
"""

import sys as _sys
import argparse as _argparse
import logging as _logging
import signal as _signal
import json as _json
import serial as _serial
import ser2tcp.serial_proxy as _serial_proxy
import ser2tcp.server_manager as _server_manager


VERSION_STR = "ser2tcp v3.0"

DESCRIPTION_STR = VERSION_STR + """
(c) 2016-2021 by pavel.revak@gmail.com
https://github.com/pavelrevak/ser2tcp
"""


def sigterm_handler(_signo, _stack_frame):
    """Raises SystemExit(0)"""
    _sys.exit(0)


def main():
    """Main"""
    _signal.signal(_signal.SIGTERM, sigterm_handler)
    _signal.signal(_signal.SIGINT, sigterm_handler)
    parser = _argparse.ArgumentParser(description=DESCRIPTION_STR)
    parser.add_argument('-V', '--version', action='version', version=VERSION_STR)
    parser.add_argument(
        '-v', '--verbose', action='count', default=0,
        help="Increase verbosity")
    parser.add_argument(
        '-c', '--config', required=True,
        help="configuration in JSON format")
    args = parser.parse_args()

    _logging.basicConfig(format='%(asctime)-15s %(levelname)s : %(message)s')
    log = _logging.getLogger('ser2tcp')
    log.setLevel((30, 20, 10)[min(2, args.verbose)])

    configuration = []
    with open(args.config, "r", encoding='utf-8') as config_file:
        configuration = _json.load(config_file)

    servers_manager = _server_manager.ServersManager()
    try:
        for config in configuration:
            servers_manager.add_server(_serial_proxy.SerialProxy(config, log))
        while True:
            servers_manager.process()
    except OSError as err:
        log.info(err)
    finally:
        log.info("Exiting..")
        servers_manager.close()
