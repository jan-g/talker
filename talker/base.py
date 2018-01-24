import logging
import selectors
import socket
import time

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

    def read(self):
        """If the socket has something to read, handle that read and propagate events"""
        pass

    def has_output(self):
        return False

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
        LOG.debug('Accepted new connection: %s %s', client, addr)
        client.setblocking(False)
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

    def read(self):
        try:
            input = self.socket.recv(16384)
        except ConnectionError:
            # This was an outgoing connection that failed, or a reset socket,
            # or what-have-you.
            self.close()
            return
        if len(input) == 0:
            # Peer shutdown
            self.close()
        else:
            self.in_buffer += input
            self.handle_input()

    def handle_input(self):
        LOG.debug("Received some bytes from the client: %s", self.in_buffer.decode("utf-8"))
        self.in_buffer = bytes()

    def has_output(self):
        return len(self.out_buffer) > 0

    def write(self):
        if len(self.out_buffer) > 0:
            outlen = self.socket.send(self.out_buffer)
            self.out_buffer = self.out_buffer[outlen:]

    def queue_output(self, output):
        self.out_buffer += output


def _make_server_socket(host, port):
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((host, port))
    s.setblocking(False)
    s.listen(5)
    return s


def _make_client_socket(host, port):
    s = socket.socket()
    s.setblocking(False)
    try:
        s.connect((host, port))
    except BlockingIOError:
        pass
    return s


class Server(object):
    """You may want to override this

    In particular:
    extend __init__
    add additional methods used by the client factory
    """
    TICK = 1

    def __init__(self, host='0.0.0.0', port=8889, client_factory=ClientSocket,
                 make_server_socket=_make_server_socket,
                 make_client_socket=_make_client_socket,
                 selector=selectors.DefaultSelector):
        self.make_server_socket = make_server_socket
        self.make_client_socket = make_client_socket
        self.selector = selector()
        self.sockets = set()
        self.add_socket(ServerSocket(server=self, socket=make_server_socket(host, port), client_factory=client_factory))

    def loop(self):
        last_tick = time.time()
        while len(self.sockets) > 0:
            self.process_sockets()

            now = time.time()
            if now - last_tick >= self.TICK:
                self.tick()
                last_tick = now

    def process_sockets(self):
        for s in self.sockets:
            if s.has_output():
                self.selector.modify(s, selectors.EVENT_READ | selectors.EVENT_WRITE)
            else:
                self.selector.modify(s, selectors.EVENT_READ)

        events = self.selector.select(self.TICK)

        for r, m in events:
            if m & selectors.EVENT_READ and r.fileobj in self.sockets:
                r.fileobj.read()
        for w, m in events:
            if m & selectors.EVENT_WRITE and w.fileobj in self.sockets:
                w.fileobj.write()

    def add_socket(self, socket):
        self.sockets.add(socket)
        self.selector.register(socket, selectors.EVENT_READ | selectors.EVENT_WRITE)
        socket.handle_new()

    def remove_socket(self, socket):
        self.sockets.remove(socket)
        self.selector.unregister(socket)
        socket.handle_close()

    def tick(self):
        pass


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
