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
    def command_peers(self):
        peers = self.server.list_peers()
        self.output_line("There are {} peers directly connected".format(len(peers)))
        for peer in peers:
            self.output_line(str(peer))

    def command_peer_listen(self, host, port):
        port = int(port)
        LOG.info("Adding PeerServer at %s %d", host, port)
        s = talker.base.make_socket(host, port)
        peer_server = talker.base.ServerSocket(server=self.server, socket=s, client_factory=PeerClient)
        self.server.add_client(peer_server)

    def command_peer_connect(self, host, port):
        port = int(port)
        LOG.info("Adding PeerClient at %s %d", host, port)
        peer = PeerClient.connect(self.server, host, port)
        self.server.add_client(peer)

    def command_peer_kill(self, host, port):
        port = int(port)
        LOG.info("Killing PeerClient at %s %d", host, port)
        for peer in self.server.list_peers():
            if peer.addr == (host, port):
                self.output_line("Shutting down {}".format(peer))
                peer.close()

    def command_broadcast(self, *args):
        message = ' '.join(args)
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

    def __init__(self, client_factory=Client, peer_id=None, **kwargs):
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


class PeerObserver:
    def __init__(self, server=None):
        self._server = server

    @property
    def server(self):
        return self._server

    @classmethod
    def prefix(cls):
        return cls.__name__

    def unicast(self, peer, payload):
        self.server.peer_unicast(peer, payload, self)

    def broadcast(self, payload):
        self.server.peer_broadcast(payload, target=self)

    def peer_added(self, peer):
        LOG.debug('New peer detected by %s: %s', self, peer)

    def peer_removed(self, peer):
        LOG.debug('Peer removed by %s: %s', self, peer)

    def notify(self, peer, source, id, message):
        LOG.debug('Message %s received from %s via %s: %s', id, source, peer, message)


class SpeechObserver(PeerObserver):

    def notify(self, _, source, id, message):
        name, line = message.split('|', 1)
        self.server.tell_speakers("{}: {}".format(name, line))


class SpeakerClient(Client):
    def speak(self, line):
        self.server.peer_broadcast("{}|{}".format(self.name, line), target=SpeechObserver)

    def command_reachable(self):
        helper = self.server.observer(TopologyObserver)
        reachable = helper.reachable()
        self.output_line("There are {} reachable peers:".format(len(reachable)))
        for node in reachable:
            self.output_line(node)

    COMMANDS = dict(Client.COMMANDS)
    COMMANDS.update({
        "/reachable": command_reachable,
    })


def speaker_server(**kwargs):
    s = Server(client_factory=SpeakerClient, **kwargs)
    s.observe_broadcast(SpeechObserver(s))
    s.observe_broadcast(TopologyObserver(s))
    return s


class TopologyObserver(PeerObserver):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # We track all the peers we know about, keeping track of who they
        # are directly connected to, and the most recent update we have received from them.
        self.peer_ids = {}
        self.topology = {self.server.peer_id: (0, set())}
        self.calculate_reachable_peers()

    I_AM = 'i-am'
    I_SEE = 'i-see'

    def peer_added(self, peer):
        LOG.debug('New peer detected by %s: %s', self, peer)
        self.unicast(peer, TopologyObserver.I_AM)

    def peer_removed(self, peer):
        LOG.debug('Peer removed: %s', peer)
        if peer in self.peer_ids:
            del self.peer_ids[peer]
        self.broadcast_new_neighbours()

    def broadcast_new_neighbours(self):
        self.broadcast(TopologyObserver.I_SEE + '|' + ';'.join(self.peer_ids.values()))

    def notify(self, peer, source, id, message):
        LOG.debug('Topology update %d received from %s: %s', id, source, message)
        kind, _, payload = message.partition('|')
        if kind == TopologyObserver.I_AM:
            self.process_i_am(peer, source)
        elif kind == TopologyObserver.I_SEE:
            self.process_i_see(source, id, payload)
        else:
            LOG.error('Unknown topology message %s from %s', message, peer)

    def process_i_am(self, peer, source):
        self.peer_ids[peer] = source
        self.broadcast_new_neighbours()

    def process_i_see(self, source, id, payload):
        if payload == '':
            neighbours = set()
        else:
            neighbours = set(payload.split(';'))

        if source not in self.topology:
            self.topology[source] = (id, neighbours)
            self.calculate_reachable_peers()
            # We've just heard about a new server joining the network, so let them know about us.
            self.broadcast_new_neighbours()

        elif self.topology[source][0] < id:
            old_neighbours = self.topology[source][1]
            self.topology[source] = (id, neighbours)
            if old_neighbours != neighbours:
                self.calculate_reachable_peers()

    def calculate_reachable_peers(self):
        LOG.debug('Calculating reachability from topology, initial is %s', self.topology)
        # Start with ourselves, work out who is reachable on the current network
        reachable = set()
        new = {self.server.peer_id}

        while len(new) != 0:
            reachable.update(new)
            added = new
            new = set()
            for node in added:
                if node in self.topology:
                    new.update(self.topology[node][1])
            new.difference_update(reachable)

        LOG.debug('Calculated reachable peers: %s', reachable)
        for node in set(self.topology):
            if node not in reachable:
                LOG.debug('  deleting node %s', node)
                del self.topology[node]
        LOG.debug('Final topology is %s', self.topology)

    def reachable(self):
        return set(self.topology)
