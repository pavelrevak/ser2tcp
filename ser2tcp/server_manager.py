"""Server manager"""

import select as _select


class ServersManager():
    """Servers manager"""
    def __init__(self):
        self._servers = []
        self._running = False

    def stop(self, _signo=None, _stack_frame=None):
        """Stop the server manager loop"""
        self._running = False

    def run(self):
        """Run the server manager loop"""
        self._running = True
        while self._running:
            self.process()
        self.close()

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
