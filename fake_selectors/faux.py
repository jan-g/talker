"""
Supply a completely in-process implementation of socket and selector classes.

Each socket has a pair of queues associated it - these hold incoming and
outgoing messages.

The selector uses the _recv_ready and _send_ready methods to control which
sockets are returned as being ready to read from or write to, respectively.

User code can inspect those queues to inject additional traffic or examine
messages in-flow. Additionally, it's possible to externally block a queue from
delivering its contents; this can be used to chose the relative ordering of
messages.

TODO: messages may be marked as having a causal originator
"""

import collections
import logging
import socket

LOG = logging.getLogger(__name__)


class Mux:
    def __init__(self):
        self.listeners = {}    # addr -> Fakesocket
        self.connections = {}  # (from, to) -> FakeSocket (the receiver)

    def accept(self, server, peer):
        conn = FakeSocket(self)
        conn.sock_addr = server.sock_addr
        conn.peer_addr = peer.sock_addr
        self.connections[conn.sock_addr, conn.peer_addr] = peer
        self.connections[conn.peer_addr, conn.sock_addr] = conn
        return conn, peer.sock_addr

    def connect(self, client, addr):
        server = self.listeners[addr]
        server._enqueue(client)

    def register_listener(self, server):
        assert server.sock_addr not in self.listeners
        self.listeners[server.sock_addr] = server

    def close_listener(self, server):
        del self.listeners[server.sock_addr]

    def close_connected(self, sock):
        # Enqueue a closing packet at the other end
        peer = self.connections[sock.self_addr, sock.peer_addr]
        peer._enqueue(b'')
        del self.connections[sock.self_addr, sock.peer_addr]

    def send(self, sock, data):
        self.connections[sock.self_addr, sock.peer_addr]._enqueue(data)


class StateError(BaseException):
    pass


class FakeSocket:
    def __init__(self, mux):
        self.mux = mux

        self.sock_addr = None
        self.peer_addr = None
        self.open = True
        self.listening = False
        self.connected = False
        self.peer_shutdown = False

        self.blocking = True

        self.incoming_pipe = collections.deque()
        self.incoming_limit = 0

    def _enqueue(self, datagram):
        self.incoming_pipe.append(datagram)

    def accept(self):
        assert self.open
        assert self.listening

        if self.incoming_limit == 0:
            if not self.blocking:
                raise BlockingIOError()
            raise StateError('accept called on socket with no asserted input')

        if self.incoming_limit is not None:
            self.incoming_limit -= 1

        peer = self.incoming_pipe.popleft()
        return self.mux.accept(self, peer)

    def bind(self, address):
        assert self.sock_addr is None
        assert self.open
        self.sock_addr = address

    def close(self):
        if self.listening:
            self.mux.close_listener(self)
            self.listening = False

        if self.connected:
            self.mux.close_conencted(self)
            self.connected = False

        self.open = False

    def connect(self, address):
        assert self.peer_addr is None
        assert self.open

        self.connected = True
        self.peer_addr = address
        self.mux.connect(self, address)

    def connect_ex(self, address):
        raise NotImplementedError()

    def detach(self):
        raise NotImplementedError()

    def fileno(self):
        raise NotImplementedError()

    def getpeername(self):
        assert self.open
        return self.peer_addr

    def getsockname(self):
        assert self.open
        return self.sock_addr

    def getsockopt(self, level, option, buffersize=None):
        raise NotImplementedError()

    def gettimeout(self):
        raise NotImplementedError()

    def listen(self, backlog=None):
        assert self.open
        assert not self.connected
        assert not self.listening

        self.listening = True
        self.mux.register_listener(self)

    def recv(self, buffersize, flags=None):
        assert self.open
        assert self.connected
        assert flags is None

        if self.peer_shutdown:
            return b''

        if self.incoming_limit == 0:
            if not self.blocking:
                raise BlockingIOError()
            raise StateError('recv called on socket with no asserted input')

        if self.incoming_limit is not None:
            self.incoming_limit -= 1

        packet = self.incoming_pipe.popleft()
        assert isinstance(packet, bytes)
        assert len(packet) <= buffersize

        if len(packet) == 0:
            self.peer_shutdown = True

        return packet

    def recvfrom(self, buffersize, flags=None):
        raise NotImplementedError()

    def recvfrom_into(self, buffer, nbytes=None, flags=None):
        raise NotImplementedError()

    def recvmsg(self, bufsize, ancbufsize=None, flags=None):
        raise NotImplementedError()

    def recvmsg_into(self, buffers, ancbufsize=None, flags=None):
        raise NotImplementedError()

    def recv_into(self, buffer, nbytes=None, flags=None):
        raise NotImplementedError()

    def send(self, data, flags=None):
        assert self.open
        assert self.connected
        assert flags is None

        self.mux.send(self, data)

    def sendall(self, data, flags=None):
        raise NotImplementedError()

    def sendmsg(self, buffers, ancdata=None, flags=None, address=None):
        raise NotImplementedError()

    def sendto(self, data, flags=None, *args, **kwargs):
        raise NotImplementedError()

    def setblocking(self, flag):
        self.blocking = flag

    def setsockopt(self, level, option, value):
        if (level, option) == (socket.SOL_SOCKET, socket.SO_REUSEADDR):
            return
        raise NotImplementedError()

    def settimeout(self, timeout):
        raise NotImplementedError()

    def shutdown(self, flag):
        raise NotImplementedError()


class Selector:
    def register(self, fileobj, events, data=None):
        raise NotImplementedError()

    def unregister(self, fileobj):
        raise NotImplementedError()

    def modify(self, fileobj, events, data=None):
        raise NotImplementedError()

    def select(self, timeout=None):
        raise NotImplementedError()

    def close(self):
        raise NotImplementedError()

    def get_key(self, fileobj):
        raise NotImplementedError()

    def get_map(self):
        raise NotImplementedError()

    def __enter__(self):
        raise NotImplementedError()

    def __exit__(self, *args):
        raise NotImplementedError()
