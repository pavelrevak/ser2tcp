"""Connection SSL"""

import ssl as _ssl

import ser2tcp.connection_tcp as _connection_tcp


class SslHandshakeError(Exception):
    """SSL handshake failed"""


class ConnectionSsl(_connection_tcp.ConnectionTcp):
    """SSL/TLS connection"""

    def __init__(
            self, connection, ser, send_timeout=None, buffer_limit=None,
            log=None, ssl_context=None):
        sock, addr = connection
        self._socket = None
        try:
            ssl_sock = ssl_context.wrap_socket(sock, server_side=True)
        except _ssl.SSLError as err:
            sock.close()
            raise SslHandshakeError(f"SSL handshake failed: {err}") from err
        super().__init__(
            (ssl_sock, addr), ser, send_timeout, buffer_limit, log)

    def _log_connected(self):
        self._log.info("Client connected: %s:%d SSL", *self._addr)
