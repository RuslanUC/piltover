try:
    from http.server import HTTPSServer
except ImportError:
    from http.server import HTTPServer

    # https://github.com/python/cpython/blob/025fe552c462796b32d57c34987355d04aa55ed5/Lib/http/server.py#L132
    class HTTPSServer(HTTPServer):
        def __init__(self, server_address, RequestHandlerClass,
                     bind_and_activate=True, *, certfile, keyfile=None,
                     password=None, alpn_protocols=None):
            try:
                import ssl
            except ImportError:
                raise RuntimeError("SSL module is missing; "
                                   "HTTPS support is unavailable")

            self.ssl = ssl
            self.certfile = certfile
            self.keyfile = keyfile
            self.password = password
            # Support by default HTTP/1.1
            self.alpn_protocols = (
                ["http/1.1"] if alpn_protocols is None else alpn_protocols
            )

            super().__init__(server_address,
                             RequestHandlerClass,
                             bind_and_activate)

        def server_activate(self):
            """Wrap the socket in SSLSocket."""
            super().server_activate()
            context = self._create_context()
            self.socket = context.wrap_socket(self.socket, server_side=True)

        def _create_context(self):
            """Create a secure SSL context."""
            context = self.ssl.create_default_context(self.ssl.Purpose.CLIENT_AUTH)
            context.load_cert_chain(self.certfile, self.keyfile, self.password)
            context.set_alpn_protocols(self.alpn_protocols)
            return context
