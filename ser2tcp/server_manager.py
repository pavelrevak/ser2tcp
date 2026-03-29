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

    def remove_server(self, server):
        """Remove server"""
        self._servers.remove(server)

    def process(self):
        """Process all servers"""
        read_list = []
        write_list = []
        for server in self._servers:
            read_list.extend(server.read_sockets())
            write_list.extend(server.write_sockets())
        ready = _select.select(read_list, write_list, [], .1)
        read_sockets, write_sockets = ready[0], ready[1]
        for server in self._servers:
            if read_sockets:
                server.process_read(read_sockets)
            if write_sockets:
                server.process_write(write_sockets)
            server.process_stale()

    def close(self):
        """Close all servers"""
        for server in self._servers:
            server.close()
