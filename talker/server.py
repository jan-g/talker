import logging
import select
import socket


LOG = logging.getLogger(__name__)


class Socket(object):
    def has_output(self):
        return False

    def read(self, server, socket):
        pass

    def write(self, server, socket):
        pass


class ServerSocket(Socket):
    def __init__(self, client_factory):
        self.client_factory = client_factory

    def read(self, server, socket):
        client, addr = socket.accept()
        server.add_client(client, self.client_factory(addr))


class ClientSocket(Socket):
    """You should override this, in particular these methods:
    handle_new
    handle_input
    handle_close
    """
    def __init__(self, addr):
        self.addr = addr
        self.in_buffer = bytes()
        self.out_buffer = bytes()

    def has_output(self):
        return len(self.out_buffer) > 0

    def read(self, server, socket):
        input = socket.recv(16384)
        if len(input) == 0:
            # Peer shutdown
            self.handle_close(server, socket)
        else:
            self.in_buffer += input
            self.handle_input(server, socket)

    def handle_close(self, server, socket):
        LOG.debug("Client is closed: %s", self.addr)
        socket.close()
        server.remove_client(socket, self)

    def handle_input(self, server, socket):
        LOG.debug("Received some bytes from the client: %s", self.in_buffer.decode("utf-8"))
        self.in_buffer = bytes()

    def write(self, server, socket):
        if len(self.out_buffer) > 0:
            outlen = socket.send(self.out_buffer)
            self.out_buffer = self.out_buffer[outlen:]

    def queue_output(self, output):
        self.out_buffer += output

    def handle_new(self, server, socket):
        LOG.debug("New client: %s", self.addr)
        self.queue_output(bytes('Welcome, {}\r\n'.format(self.addr), 'utf-8'))


class Server(object):
    """You may want to override this

    In particular:
    extend __init__
    add additional methods used by the client factory
    """
    def __init__(self, host='0.0.0.0', port=8889, client_factory=ClientSocket):
        self.clients = {self.make_socket(host, port): ServerSocket(client_factory)}

    def make_socket(self, host, port):
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        s.listen(5)
        return s

    def loop(self):
        while len(self.clients) > 0:
            readers = set(self.clients)
            writers = {c for c in self.clients if self.clients[c].has_output()}
            readable, writable, x = select.select(readers, writers, [])
            for r in readable:
                self.clients[r].read(self, r)

            for w in writable:
                self.clients[w].write(self, w)

    def add_client(self, socket, client):
        self.clients[socket] = client
        client.handle_new(self, socket)

    def remove_client(self, socket, client):
        del self.clients[socket]

    def accept(self, socket):
        return None
