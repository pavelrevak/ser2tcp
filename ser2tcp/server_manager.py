"""Server manager"""

import select as _select


class ServersManager():
    """Servers manager"""
    def __init__(self):
        self._servers = []

    def add_server(self, server):
        """Add server"""
        self._servers.append(server)

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


