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
import selectors
import socket

LOG = logging.getLogger(__name__)


class Mux:
    def __init__(self):
        self.listeners = {}    # addr -> Fakesocket
        self.connected = set() # (from, to) -> FakeSocket (the receiver)
        self.fd_pool = set(range(10, 1000))
        self.fd_map = {}
        self.free_ports = set(range(30000, 32000))

    def get_fd(self, sock):
        fd = self.fd_pool.pop()
        self.fd_map[fd] = sock
        return fd

    def release_fd(self, fd):
        del self.fd_map[fd]
        self.fd_pool.add(fd)

    def auto_bind(self):
        return '0.0.0.0', self.free_ports.pop()

    def accept(self, server, peer):
        assert peer.state == FakeSocket.CONNECTING
        conn = FakeSocket(self)
        conn.addr = server.addr
        conn.peer = peer
        conn.state = FakeSocket.CONNECTED
        peer.peer = conn
        peer.state = FakeSocket.CONNECTED
        self.connected.add(conn)
        self.connected.add(peer)
        return conn, peer.addr

    def connect(self, client, addr):
        server = self.listeners[addr]
        server._enqueue(client)

    def register_listener(self, server):
        assert server.addr not in self.listeners
        self.listeners[server.addr] = server

    def close_listener(self, server):
        del self.listeners[server.addr]
        self.release_fd(server.fileno())

    def close_connected(self, sock):
        # Enqueue a closing packet at the other end
        peer = self.connections[sock.self_addr, sock.peer_addr]
        peer._enqueue(b'')
        del self.connections[sock.self_addr, sock.peer_addr]
        self.release_fd(sock.fileno())

    def send(self, sock, data):
        while b'\r\n' in data:
            packet, crlf, data = data.partition(b'\r\n')
            sock.peer._enqueue(packet + crlf)

    def unblocked_data_outstanding(self):
        return any(sock._readable() for sock in self.fd_map.values())


class StateError(BaseException):
    pass


class FakeSocket:
    UNATTACHED = 'unattached'
    CONNECTING = 'connecting'
    LISTENING = 'listening'
    CONNECTED = 'connected'

    def __init__(self, mux):
        self.mux = mux

        self.addr = None
        self.peer = None
        self.open = True
        self.state = FakeSocket.UNATTACHED
        self.peer_shutdown = False

        self.blocking = True

        self.incoming_pipe = collections.deque()
        self.incoming_limit = None

        self.fd = mux.get_fd(self)

    def __str__(self):
        result = '{}({})'.format(self.state, self.addr)
        if self.state == FakeSocket.CONNECTING:
            result += ' -> ({})'.format(self.peer_addr)
        elif self.state == FakeSocket.CONNECTED:
            result += ' => {}({})'.format(self.peer.state, self.peer.addr)
        result += ' {}{}#{}'.format('R' if self._readable() else '',
                                    'W' if self._writable() else '',
                                    len(self.incoming_pipe))
        return result

    __repr__ = __str__

    def _enqueue(self, datagram):
        self.incoming_pipe.append(datagram)

    def accept(self):
        assert self.open
        assert self.state == FakeSocket.LISTENING

        if self.incoming_limit == 0:
            if not self.blocking:
                raise BlockingIOError()
            raise StateError('accept called on socket with no asserted input')

        if self.incoming_limit is not None:
            self.incoming_limit -= 1

        peer = self.incoming_pipe.popleft()
        return self.mux.accept(self, peer)

    def bind(self, address):
        assert self.addr is None
        assert self.open
        self.addr = address

    def close(self):
        if self.state == FakeSocket.LISTENING:
            self.mux.close_listener(self)
            self.state = None

        elif self.state == FakeSocket.CONNECTED:
            self.mux.close_conencted(self)
            self.state = None

        self.open = False

    def connect(self, address):
        assert self.peer is None
        assert self.open
        assert self.state == FakeSocket.UNATTACHED

        if self.addr is None:
            self.addr = self.mux.auto_bind()

        self.state = FakeSocket.CONNECTING
        self.peer_addr = address
        self.mux.connect(self, address)

    def connect_ex(self, address):
        raise NotImplementedError()

    def detach(self):
        raise NotImplementedError()

    def fileno(self):
        return self.fd

    def getpeername(self):
        assert self.open
        return self.peer.addr

    def getsockname(self):
        assert self.open
        return self.addr

    def getsockopt(self, level, option, buffersize=None):
        raise NotImplementedError()

    def gettimeout(self):
        raise NotImplementedError()

    def listen(self, backlog=None):
        assert self.open
        assert self.state == FakeSocket.UNATTACHED

        self.state = FakeSocket.LISTENING
        self.mux.register_listener(self)

    def _readable(self):
        return (self.state in (FakeSocket.LISTENING, FakeSocket.CONNECTED) and
                (self.incoming_limit is None or self.incoming_limit > 0) and
                len(self.incoming_pipe) > 0)

    def _writable(self):
        return self.state == FakeSocket.CONNECTED and not self.peer_shutdown

    def recv(self, buffersize, flags=None):
        assert self.open
        assert self.state == FakeSocket.CONNECTED
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
        assert self.state == FakeSocket.CONNECTED
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
    def __init__(self, mux):
        self.mux = mux
        self.registry = {}

    def register(self, fileobj, events, data=None):
        if not events or events & ~(selectors.EVENT_READ | selectors.EVENT_WRITE):
            raise ValueError()
        if fileobj in self.registry:
            raise KeyError()
        self.registry[fileobj] = (events, data)

    def unregister(self, fileobj):
        del self.registry[fileobj]

    def modify(self, fileobj, events, data=None):
        if not events or events & ~(selectors.EVENT_READ | selectors.EVENT_WRITE):
            raise ValueError()
        if fileobj not in self.registry:
            raise KeyError()
        self.registry[fileobj] = (events, data)

    def select(self, timeout=None):
        LOG.debug('Entering select, registry = %s', self.registry)
        result = []
        for fileobj in self.registry:
            sock = self.mux.fd_map[fileobj.fileno()]
            events, data = self.registry[fileobj]
            value = 0
            if events & selectors.EVENT_READ and sock._readable():
                value |= selectors.EVENT_READ
            if events & selectors.EVENT_WRITE and sock._writable():
                value |= selectors.EVENT_WRITE
            if value != 0:
                result.append((selectors.SelectorKey(fileobj, None, events, data), value))
        LOG.debug('Select returns: %s', result)
        return result

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
