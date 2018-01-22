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

LOG = logging.getLogger(__name__)


class Mux:
    def __init__(self):
        pass

    def connect(self, client, address):
        raise NotImplementedError()

    def register_listener(self, server):
        raise NotImplementedError()

    def close_listener(self, server):
        raise NotImplementedError()

    def close_connected(self, sock):
        raise NotImplementedError()

    def send(self, source, data):
        raise NotImplementedError()


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
            assert not self.blocking
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
        return super().sendall(data, flags)

    def sendmsg(self, buffers, ancdata=None, flags=None, address=None):
        return super().sendmsg(buffers, ancdata, flags, address)

    def sendto(self, data, flags=None, *args, **kwargs):
        return super().sendto(data, flags, *args, **kwargs)

    def setblocking(self, flag):
        return super().setblocking(flag)

    def setsockopt(self, level, option, value):
        return super().setsockopt(level, option, value)

    def settimeout(self, timeout):
        return super().settimeout(timeout)

    def shutdown(self, flag):
        return super().shutdown(flag)

    def _accept(self):
        return super()._accept()

    def __del__(self, *args, **kwargs):
        return super().__del__(*args, **kwargs)

    def __getattribute__(self, *args, **kwargs):
        return super().__getattribute__(*args, **kwargs)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @staticmethod
    def __new__(*args, **kwargs):
        return super().__new__(*args, **kwargs)

    def __repr__(self, *args, **kwargs):
        return super().__repr__(*args, **kwargs)
