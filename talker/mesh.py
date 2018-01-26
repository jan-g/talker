"""
Add the capability to host a network of server peers.

This begins with three things: adding a PeerServer socket type,
extending the server to keep track of Peers (including connecting
a client socket), and the Client extensions to add commands to manage those.
"""

import binascii
import logging
import os
import time

import talker.server

LOG = logging.getLogger(__name__)


class PeerClient(talker.base.LineBuffered):

    @classmethod
    def connect(cls, server, host, port):
        s = server.make_client_socket(host, port)
        peer = cls(addr=(host, port), server=server, socket=s)
        return peer

    def handle_new(self):
        LOG.debug("New peer connection from %s", self)
        self.server.register_peer(self)

    def handle_close(self):
        LOG.debug("Peer connection %s closed", self)
        self.server.unregister_peer(self)

    def handle_line(self, line):
        """Handle a line of input. It'll be in string form"""
        LOG.debug("Received line of input from peer %s: %s", self, line)
        self.server.peer_receive(self, line)


class Server(talker.server.Server):
    MESSAGE_CACHE_EXPIRY = 1

    def __init__(self, client_factory=talker.server.Client, peer_id=None, **kwargs):
        super().__init__(client_factory=client_factory, **kwargs)

        # Each server has a random, and hopefully unique, id
        if peer_id is None:
            self.peer_id = binascii.b2a_hex(os.urandom(10)).decode('utf-8')
        else:
            self.peer_id = peer_id

        # These are other servers directly connected to this one
        self.peers = set()

        # As a message floods the peer network, we notify any local handlers
        self.broadcast_observers = {}

        # We add a unique identifier to each message that we originate
        self.message_id = 0

        # We keep track of recently-seen messages, only handling or passing them on once.
        # We keep the current set and the previous set, and rotate those after a timeout
        self.seen = [set(), set()]
        self.last_rotation = time.time()

    def register_peer(self, peer):
        LOG.info("New peer added: %s", peer)
        self.peers.add(peer)
        for o in self.broadcast_observers.values():
            o.peer_added(peer)

    def unregister_peer(self, peer):
        LOG.info("Peer removed: %s", peer)
        self.peers.remove(peer)
        for o in self.broadcast_observers.values():
            o.peer_removed(peer)

    def list_peers(self):
        return set(self.peers)

    def observe_broadcast(self, observer):
        self.broadcast_observers[observer.prefix()] = observer

    def observer(self, cls):
        return self.broadcast_observers.get(cls.prefix())

    def notify_observers(self, peer, source, id, message):
        """A message has arrived via a particular peer.

        It originates at some source, has a message id and a payload."""
        target, _, payload = message.partition('|')
        if target in self.broadcast_observers:
            self.broadcast_observers[target].notify(peer, source, id, payload)

    def peer_broadcast(self, payload, target=None):
        """Originate a new message to broadcast

        We notify local observers, too"""
        if target is None:
            message = payload
        else:
            message = target.prefix() + '|' + payload

        self.message_id += 1
        self.peer_propagate(self._format_peer_line(self.peer_id, self.message_id, message))
        self.notify_observers(None, self.peer_id, self.message_id, message)

    def peer_unicast(self, peer, payload, target):
        """Send a message to a single, directly-connected peer

        Do not notify local observers"""
        if target is None:
            message = payload
        else:
            message = target.prefix() + '|' + payload

        self.message_id += 1
        self.peer_propagate(self._format_peer_line(self.peer_id, self.message_id, message, broadcast=False), include={peer})

    def peer_propagate(self, line, include=None, exclude=set()):
        """Pass a received message on, if necessary"""
        if include is None:
            include = self.peers
        for peer in include:
            if peer not in exclude:
                peer.output_line(line)

    def _parse_peer_line(self, line):
        """Turn a line of input into source, message id, message, and broadcast flag"""
        if line.startswith('!'):
            source, message_id, payload = line[1:].split('|', 2)
            return source, int(message_id), payload, False
        else:
            source, message_id, payload = line.split('|', 2)
            return source, int(message_id), payload, True

    def _format_peer_line(self, id, message_id, message, broadcast=True):
        if broadcast:
            return str(id) + '|' + str(message_id) + '|' + str(message)
        else:
            return '!' + str(id) + '|' + str(message_id) + '|' + str(message)

    def peer_receive(self, peer, line):
        """A peer tells us something.

        If we've not heard it before, handle it locally.
        That means queuing it for propagation, as well as passing it to any listeners."""

        source, id, message, broadcast = self._parse_peer_line(line)

        try:
            # Was this something we said?
            if source == self.peer_id:
                # If so, it's already been handled
                return

            # Have we seen this message before?
            key = (source, id)
            if any(key in cache for cache in self.seen):
                # If so, it's been handled!
                return

            # Make a note that we've seen this
            self.seen[0].add(key)

            # Queue up the message for propagation around the network, then handle it locally
            if broadcast:
                self.peer_propagate(line, exclude={peer})
            self.notify_observers(peer, source, id, message)

        finally:
            # Whatever happens, let's rotate the set of seen messages if necessary.
            now = time.time()
            if now - self.last_rotation >= self.MESSAGE_CACHE_EXPIRY:
                self.seen = [set(), self.seen[0]]
                self.last_rotation = now

    def tick(self):
        """Tick once every second or so"""
        for obs in self.broadcast_observers.values():
            obs.tick()


class PeerObserver:
    def __init__(self, server=None, *args, **kwargs):
        self._server = server
        self._methods = {}
        super().__init__(*args, **kwargs)  # Give mixins a chance to initialise

    @property
    def server(self):
        return self._server

    @classmethod
    def prefix(cls):
        return cls.__name__

    def register_method(self, name, call):
        self._methods[name] = call

    def unicast(self, peer, method, payload=''):
        self.server.peer_unicast(peer, method + '|' + payload, self)

    def broadcast(self, method, payload='', target=None):
        if target is None:
            target = self
        self.server.peer_broadcast(method + '|' + payload, target=target)

    def peer_added(self, peer):
        LOG.debug('New peer detected by %s: %s', self, peer)

    def peer_removed(self, peer):
        LOG.debug('Peer removed by %s: %s', self, peer)

    def notify(self, peer, source, id, message):
        LOG.debug('Message %s received from %s via %s: %s', id, source, peer, message)
        method, _, payload = message.partition('|')
        self._methods[method](peer, source, id, payload)

    def tick(self):
        pass
