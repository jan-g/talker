"""
Add the capability to host a network of server peers.

This begins with three things: adding a PeerServer socket type,
extending the server to keep track of Peers (including connecting
a client socket), and the Client extensions to add commands to manage those.
"""

import binascii
import logging
import os
import socket
import time

import talker.server
import talker.base

LOG = logging.getLogger(__name__)


class PeerClient(talker.base.LineBuffered):

    @classmethod
    def connect(cls, server, host, port):
        s = socket.socket()
        s.connect((host, port))
        peer = cls(addr=(host, port), server=server, socket=s)
        peer.handle_new()
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


class Client(talker.server.Client):
    def command_peers(self, _):
        peers = self.server.list_peers()
        self.output_line("There are {} peers directly connected".format(len(peers)))
        for peer in peers:
            self.output_line(str(peer))

    def command_peer_listen(self, args):
        host, port = args[1], int(args[2])
        LOG.info("Adding PeerServer at %s %d", host, port)
        s = talker.base.make_socket(host, port)
        peer_server = talker.base.ServerSocket(server=self.server, socket=s, client_factory=PeerClient)
        self.server.add_client(peer_server)

    def command_peer_connect(self, args):
        host, port = args[1], int(args[2])
        LOG.info("Adding PeerClient at %s %d", host, port)
        peer = PeerClient.connect(self.server, host, port)
        self.server.add_client(peer)

    def command_peer_kill(self, args):
        host, port = args[1], int(args[2])
        LOG.info("Killing PeerClient at %s %d", host, port)
        for peer in self.server.list_peers():
            if peer.addr == (host, port):
                self.output_line("Shutting down {}".format(peer))
                peer.close()

    def command_broadcast(self, args):
        message = ' '.join(args[1:])
        LOG.info("Broadcasting message: %s", message)
        self.server.peer_broadcast(message)

    COMMANDS = dict(talker.server.Client.COMMANDS)
    COMMANDS.update({
        "/peers": command_peers,
        "/peer-listen": command_peer_listen,
        "/peer-connect": command_peer_connect,
        "/peer-kill": command_peer_kill,
        "/broadcast": command_broadcast,
    })


class Server(talker.server.Server):
    MESSAGE_CACHE_EXPIRY = 1

    def __init__(self, client_factory=Client, **kwargs):
        super().__init__(client_factory=client_factory, **kwargs)

        # Each server has a random, and hopefully unique, id
        self.peer_id = binascii.b2a_hex(os.urandom(10)).decode('utf-8')

        # These are other servers directly connected to this one
        self.peers = set()

        # As a message floods the peer network, we notify any local handlers
        self.broadcast_observers = set()

        # We add a unique identifier to each message that we originate
        self.message_id = 0

        # We keep track of recently-seen messages, only handling or passing them on once.
        # We keep the current set and the previous set, and rotate those after a timeout
        self.seen = [set(), set()]
        self.last_rotation = time.time()

    def register_peer(self, peer):
        LOG.info("New peer added: %s", peer)
        self.peers.add(peer)
        for o in self.broadcast_observers:
            o.peer_added(peer)

    def unregister_peer(self, peer):
        LOG.info("Peer removed: %s", peer)
        self.peers.remove(peer)
        for o in self.broadcast_observers:
            o.peer_removed(peer)

    def list_peers(self):
        return set(self.peers)

    def observe_broadcast(self, observer):
        self.broadcast_observers.add(observer)

    def notify_observers(self, source, id, message):
        for o in self.broadcast_observers:
            o.notify(source, id, message)

    def peer_broadcast(self, message):
        """Originate a new message to broadcast

        We notify local observers, too"""
        self.message_id += 1
        self.peer_propagate(self._format_peer_line(self.peer_id, self.message_id, message))
        self.notify_observers(self.peer_id, self.message_id, message)

    def peer_propagate(self, line, exclude=[]):
        """Pass a received message on, if necessary"""
        for peer in self.peers.difference(exclude):
            peer.output_line(line)

    def _parse_peer_line(self, line):
        """Turn a line of input into source, message id, and message"""
        return tuple(line.split('|', 2))

    def _format_peer_line(self, id, message_id, message):
        return str(id) + '|' + str(message_id) + '|' + str(message)

    def peer_receive(self, peer, line):
        """A peer tells us something.

        If we've not heard it before, handle it locally.
        That means queuing it for propagation, as well as passing it to any listeners."""

        source, id, message = self._parse_peer_line(line)

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
            self.peer_propagate(line, [peer])
            self.notify_observers(source, id, message)

        finally:
            # Whatever happens, let's rotate the set of seen messages if necessary.
            now = time.time()
            if now - self.last_rotation >= self.MESSAGE_CACHE_EXPIRY:
                self.seen = [set(), self.seen[0]]
                self.last_rotation = now


class PeerObserver:
    def __init__(self, server=None):
        self._server = server

    @property
    def server(self):
        return self._server

    def peer_added(self, peer):
        LOG.debug('New peer detected: %s', peer)

    def peer_removed(self, peer):
        LOG.debug('Peer removed: %s', peer)

    def notify(self, source, id, message):
        LOG.debug('Message %s received from %s: %s', id, source, message)


class SpeechObserver(PeerObserver):
    PREFIX = 'SpeechObserver|'

    def notify(self, source, id, message):
        if not message.startswith(self.PREFIX):
            return

        name, line = message[len(self.PREFIX):].split('|', 1)

        self.server.tell_speakers("{}: {}".format(name, line))


class SpeakerClient(Client):
    def speak(self, line):
        self.server.peer_broadcast("{}{}|{}".format(SpeechObserver.PREFIX, self.name, line))


def speaker_server(**kwargs):
    s = Server(client_factory=SpeakerClient, **kwargs)
    s.observe_broadcast(SpeechObserver(s))
    return s
