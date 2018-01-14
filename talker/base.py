import logging
import select
import socket


LOG = logging.getLogger(__name__)


class Socket:
    def __init__(self, server=None, socket=None):
        super().__init__()
        self._server = server
        self._socket = socket

    @property
    def server(self):
        return self._server

    @property
    def socket(self):
        return self._socket

    def fileno(self):
        return self.socket.fileno()

    def has_output(self):
        return False

    def read(self):
        """If the socket has something to read, handle that read and propagate events"""
        pass

    def write(self):
        pass

    def close(self):
        self.socket.close()
        self.server.remove_socket(self)

    def handle_new(self):
        LOG.debug("New socket registered: %s", self)

    def handle_close(self):
        LOG.debug("Socket closed: %s", self)


class ServerSocket(Socket):
    def __init__(self, client_factory=None, **kwargs):
        super().__init__(**kwargs)
        self.client_factory = client_factory

    def read(self):
        client, addr = self.socket.accept()
        self.server.add_socket(self.client_factory(server=self.server, socket=client, addr=addr))


class ClientSocket(Socket):
    """You should override this, in particular these methods:
    handle_new
    handle_input
    handle_close
    """
    def __init__(self, addr=None, **kwargs):
        super().__init__(**kwargs)
        self.addr = addr
        self.in_buffer = bytes()
        self.out_buffer = bytes()

    def __str__(self):
        return "{}{}".format(self.__class__.__name__, self.addr)

    def has_output(self):
        return len(self.out_buffer) > 0

    def read(self):
        input = self.socket.recv(16384)
        if len(input) == 0:
            # Peer shutdown
            self.close()
        else:
            self.in_buffer += input
            self.handle_input()

    def handle_input(self):
        LOG.debug("Received some bytes from the client: %s", self.in_buffer.decode("utf-8"))
        self.in_buffer = bytes()

    def write(self):
        if len(self.out_buffer) > 0:
            outlen = self.socket.send(self.out_buffer)
            self.out_buffer = self.out_buffer[outlen:]

    def queue_output(self, output):
        self.out_buffer += output


class Server(object):
    """You may want to override this

    In particular:
    extend __init__
    add additional methods used by the client factory
    """
    def __init__(self, host='0.0.0.0', port=8889, client_factory=ClientSocket):
        self.sockets = {ServerSocket(server=self, socket=make_server_socket(host, port), client_factory=client_factory)}

    def loop(self):
        while len(self.sockets) > 0:
            readers = set(self.sockets)
            writers = {c for c in self.sockets if c.has_output()}
            readable, writable, x = select.select(readers, writers, [])
            for r in readable:
                r.read()

            for w in writable:
                w.write()

    def add_socket(self, socket):
        self.sockets.add(socket)
        socket.handle_new()

    def remove_socket(self, socket):
        self.sockets.remove(socket)
        socket.handle_close()


class LineBuffered(ClientSocket):
    """Extend the ClientSocket to add newline-delimited handling.

    At this juncture, the APi turns from using sets of bytes to using strings."""

    def handle_input(self):
        while b'\r\n' in self.in_buffer:
            line, found, self.in_buffer = self.in_buffer.partition(b'\r\n')

            # Convert bytes to a string.
            try:
                s = line.decode('utf-8')
                self.handle_line(s)
            except UnicodeDecodeError:
                LOG.warning("Client %s send non-utf-8 sequence", self.addr)

    def output_line(self, line, eol=b'\r\n'):
        """Enqueue a ilne of output to the client"""
        self.queue_output(bytes(line, 'utf-8') + eol)

    def handle_new(self):
        super().handle_new()
        self.output_line("Welcome, {}".format(self.addr))

    def handle_line(self, line):
        """Handle a line of input. It'll be in string form"""
        LOG.debug("Received line of input from client %s: %s", self.addr, line)


def make_server_socket(host, port):
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((host, port))
    s.listen(5)
    return s
