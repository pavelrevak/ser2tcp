"""Server manager"""
import logging as _logging
import select as _select

import ser2tcp.serial_proxy as _serial_proxy
import ser2tcp.conf_models as _conf_models


class ServersManager():
    """Servers manager"""
    def __init__(self, log_global: _logging.Logger, configs: _conf_models.SerialConfig=None):
        self._servers = []
        self._log_global = log_global

        if configs is not None:
            for c in configs.__root__:
                self.add_server(c)

    def add_server(self, config: _conf_models.SerialMappingInstance):
        """Add server"""
        config.create_loggers()
        self._servers.append(
            _serial_proxy.SerialProxy(config, self._log_global, config.logger)
        )

    def process(self):
        """Process all servers"""
        sockets = []
        for server in self._servers:
            sockets.extend(server.sockets())
        read_sockets = _select.select(sockets, [], [], .1)[0]
        if read_sockets:
            for server in self._servers:
                server.socket_event(read_sockets)

    def close(self):
        """Close all servers"""
        for server in self._servers:
            server.close()
