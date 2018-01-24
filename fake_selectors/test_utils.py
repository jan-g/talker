import logging
import random
import socket

from fake_selectors import faux as socks

LOG = logging.getLogger(__name__)


def run_servers(mux, *servers, max=None):
    # Count the number of times nothing has been emitted
    c = 0
    while c < 2:
        for s in servers:
            s.process_sockets()
        if mux.unblocked_data_outstanding():
            c = 0
        else:
            c += 1
        if max is not None:
            max -= 1
            if max == 0:
                LOG.warning('Breaking out of run_servers: %s', mux.fd_map.values())
                break


def run_servers_randomly(mux, *servers):
    """Run a sequence of servers, picking a random message to let through the gate each time"""
    c = 0
    while c < 2:
        ready = []
        for sock in mux.all_sockets():
            sock.incoming_limit = 0
            if len(sock.incoming_pipe) > 0:
                ready.append(sock)
        if len(ready) == 0:
            c += 1
        else:
            c = 0
            sock = random.choice(ready)
            LOG.debug('Letting through a message to %s: %r', sock, sock.incoming_pipe[0])
            sock.incoming_limit = 1
        for s in servers:
            s.process_sockets()

    for sock in mux.all_sockets():
        sock.incoming_limit = None


def make_mux():
    mux = socks.Mux()

    def _make_server_socket(host, port):
        s = socks.FakeSocket(mux)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        s.setblocking(False)
        s.listen(5)
        return s

    def _make_client_socket(host, port, record=False, send_str=False):
        s = socks.FakeSocket(mux)
        if record:
            s.text = []
            s.on_receipt = _on_receipt
        if send_str:
            orig_send = s.send
            def send(text, *args, **kwargs):
                return orig_send(bytes(text.format(*args, **kwargs), 'utf-8'))
            s.send = send
        s.setblocking(False)
        try:
            s.connect((host, port))
        except BlockingIOError:
            pass
        return s

    def _make_selector():
        return socks.Selector(mux)

    return mux, _make_server_socket, _make_client_socket, _make_selector


def _on_receipt(client, packet):
    if isinstance(packet, bytes):
        packet = packet.decode('utf-8').rstrip()
    client.text.append(packet)


def clear_client_history(*clients):
    for c in clients:
        c.text = []
