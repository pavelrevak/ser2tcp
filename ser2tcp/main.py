"""Ser2tcp
Simple proxy for connecting over TCP or telnet to serial port
"""

import sys as _sys
import json as _json
import logging as _logging
from logging import config as _logging_config
import argparse as _argparse
import signal as _signal

import ser2tcp.server_manager as _server_manager
import ser2tcp.conf_models as _conf_models


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
        help="Increase verbosity: warning (default), info (-v), debug (-vv)")
    parser.add_argument(
        '-d', '--no_logger', action='count', default=0,
        help="Disable the default logger to stdout")
    parser.add_argument(
        '-c', '--config', required=True,
        help="configuration in JSON format")
    parser.add_argument(
        '-g', '--global_log_config', required=False,
        help="global logging configuration in JSON format")
    args = parser.parse_args()

    # logger initialization
    _logging.basicConfig(format='[%(levelname)s: %(asctime)s] %(message)s (%(filename)s:%(lineno)s)')
    log = _logging.getLogger('ser2tcp')
    log.setLevel((_logging.WARNING, _logging.INFO, _logging.DEBUG)[min(2, args.verbose)])

    if args.global_log_config:
        with open(args.global_log_config) as f:
            cfg = _json.load(f)
        
        _logging_config.dictConfig(cfg)
        log = _logging.getLogger('ser2tcp')
        log.debug(f"global log config:\n{cfg}")
    elif args.no_logger:
        log.disabled = True

    # serial port config initialization and parsing
    serial_configuration = _conf_models.SerialConfig.parse_file(
        path=args.config,
        encoding='utf-8',
    )

    log.info(f"Starting ser2tcp with configuration:\n{serial_configuration}")

    servers_manager = _server_manager.ServersManager(log, serial_configuration)
    
    while True:
        servers_manager.process()
    
    log.info("Exiting..")
    servers_manager.close()
