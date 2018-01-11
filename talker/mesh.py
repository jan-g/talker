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

    COMMANDS = dict(talker.server.Client.COMMANDS)
    COMMANDS.update({
        "/peers": command_peers,
        "/peer-listen": command_peer_listen,
        "/peer-connect": command_peer_connect,
        "/peer-kill": command_peer_kill,
    })


class Server(talker.server.Server):
    def __init__(self, client_factory=Client, **kwargs):
        super().__init__(client_factory=client_factory, **kwargs)
        self.peers = set()
        self.peer_id = binascii.b2a_hex(os.urandom(10))

    def register_peer(self, peer):
        LOG.info("New peer added: %s", peer)
        self.peers.add(peer)

    def unregister_peer(self, peer):
        LOG.info("Peer removed: %s", peer)
        self.peers.remove(peer)

    def list_peers(self):
        return set(self.peers)
