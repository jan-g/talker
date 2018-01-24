import logging
import random

import talker.distributed

from fake_selectors.test_utils import run_servers, run_servers_randomly, make_mux, clear_client_history

LOG = logging.getLogger(__name__)


def setup_module():
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger('fake_selectors.faux').setLevel(logging.WARNING)


def test_network_1():
    mux, servers, clients = construct_network(2)
    name_clients(mux, servers, clients)

    clear_client_history(*clients)
    clients[1].send('/peer-connect 0.0.0.0 2000\r\n')
    run_servers(mux, *servers)  # This'll error out
    clients[1].send('/peers\r\n')
    run_servers(mux, *servers)  # No peers
    assert ['There are 0 peers directly connected'] == clients[1].text

    peer_listen(mux, servers, clients)

    clients[1].send('/peer-connect 0.0.0.0 2000\r\n')
    run_servers_randomly(mux, *servers)

    clear_client_history(*clients)
    clients[0].send('/peers\r\n')
    clients[1].send('/peers\r\n')
    run_servers_randomly(mux, *servers)  # Should have a pair of peers

    assert ['There are 1 peers directly connected'] == clients[0].text[-2:-1]
    assert ['There are 1 peers directly connected', "PeerClient('0.0.0.0', 2000)"] == clients[1].text[-2:]

    clear_client_history(*clients)
    clients[0].send('/who\r\n')
    clients[1].send('/who\r\n')
    run_servers_randomly(mux, *servers)  # Should result in a few broadcasts

    for client in clients:
        assert [
            'There are 2 users online on 2 servers:',
            '  Server: s0',
            '    client0',
            '  Server: s1',
            '    client1',
        ] == client.text


def construct_network(n):
    mux, mss, mcs, sel = make_mux()

    servers = []
    clients = []
    for i in range(n):
        server = talker.distributed.speaker_server(
            make_server_socket=mss,
            make_client_socket=mcs,
            selector=sel,
            host='0.0.0.0',
            port=1000 + i,
            peer_id='s{}'.format(i))

        servers.append(server)
        clients.append(mcs('0.0.0.0', 1000 + i, record=True, send_str=True))

    return mux, servers, clients


def name_clients(mux, servers, clients):
    run_servers(mux, *servers)
    for i, (s, c) in enumerate(zip(servers, clients)):
        c.send('/nick client{}\r\n', i)
    run_servers(mux, *servers)


def peer_listen(mux, servers, clients):
    run_servers(mux, *servers)
    for i, (s, c) in enumerate(zip(servers, clients)):
        c.send('/peer-listen 0.0.0.0 {}\r\n', 2000 + i)
    run_servers(mux, *servers)


def test_random_network():
    NUM_SERVERS = 15

    mux, servers, clients = construct_network(NUM_SERVERS)
    name_clients(mux, servers, clients)
    peer_listen(mux, servers, clients)

    for i, c in enumerate(clients):
        peer = random.randrange(NUM_SERVERS)
        print(i, '/peer-connect 0.0.0.0', 2000 + peer)
        c.send('/peer-connect 0.0.0.0 {}\r\n', 2000 + peer)

    run_servers_randomly(mux, *servers)

    # Count the number of peers. Should be 2*NUM_SERVERS
    clear_client_history(*clients)
    for c in clients:
        c.send('/peers\r\n')
    run_servers_randomly(mux, *servers)

    peers = 0
    for c in clients:
        # There are .* peers directly connected
        words = c.text[0].split()
        assert ['There', 'are'] == words[:2]
        assert ['peers', 'directly', 'connected'] == words[3:]
        peers += int(words[2])

    assert 2 * NUM_SERVERS == peers


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger('fake_selectors.faux').setLevel(logging.WARNING)
    test_random_network()
