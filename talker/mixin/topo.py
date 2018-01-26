import talker.base
import talker.server
from talker.mesh import PeerObserver, LOG, PeerClient


class TopoMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.register_command("/peers", TopoMixin.command_peers)
        self.register_command("/peer-listen", TopoMixin.command_peer_listen)
        self.register_command("/peer-connect", TopoMixin.command_peer_connect)
        self.register_command("/peer-kill", TopoMixin.command_peer_kill)
        self.register_command("/broadcast", TopoMixin.command_broadcast)
        self.register_command("/reachable", TopoMixin.command_reachable)

    def command_reachable(self):
        helper = self.server.observer(TopologyObserver)
        reachable = helper.reachable()
        self.output_line("There are {} reachable peers:".format(len(reachable)))
        for node in reachable:
            self.output_line(node)

    def command_peers(self):
        peers = self.server.list_peers()
        self.output_line("There are {} peers directly connected".format(len(peers)))
        for peer in peers:
            self.output_line(str(peer))

    def command_peer_listen(self, host, port):
        port = int(port)
        LOG.info("Adding PeerServer at %s %d", host, port)
        s = self.server.make_server_socket(host, port)
        peer_server = talker.base.ServerSocket(server=self.server, socket=s, client_factory=PeerClient)
        self.server.add_socket(peer_server)

    def command_peer_connect(self, host, port):
        port = int(port)
        LOG.info("Adding PeerClient at %s %d", host, port)
        peer = PeerClient.connect(self.server, host, port)
        self.server.add_socket(peer)

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


# This is a more complicated observer of peer-to-peer messages.
# As servers are connected to and disconnected from each other, each node
# broadcasts across the network the latest version of its connectivity
# information. TopologyObservers on each server collate this information
# and use it to form an up-to-date map of who is connected to whom.

class TopologyObserver(PeerObserver):
    I_AM = 'i-am'
    I_SEE = 'i-see'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.register_method(TopologyObserver.I_AM, self.recv_i_am)
        self.register_method(TopologyObserver.I_SEE, self.recv_i_see)
        # We track all the peers we know about, keeping track of who they
        # are directly connected to, and the most recent update we have received from them.
        self.peer_ids = {}
        self.topology = {self.server.peer_id: (0, set())}
        self.calculate_reachable_peers()

    def peer_added(self, peer):
        LOG.debug('New peer detected by %s: %s', self, peer)
        self.unicast(peer, TopologyObserver.I_AM)

    def peer_removed(self, peer):
        LOG.debug('Peer removed: %s', peer)
        if peer in self.peer_ids:
            del self.peer_ids[peer]
        self.broadcast_new_neighbours()

    def broadcast_new_neighbours(self):
        self.broadcast(TopologyObserver.I_SEE, ';'.join(self.peer_ids.values()))

    def recv_i_am(self, peer, source, id, args):
        self.peer_ids[peer] = source
        self.broadcast_new_neighbours()

    def recv_i_see(self, peer, source, id, args):
        if args == '':
            neighbours = set()
        else:
            neighbours = set(args.split(';'))

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
