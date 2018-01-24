import logging
import socket

import talker.server
import fake_selectors.faux as socks

LOG = logging.getLogger(__name__)


def setup_module():
    logging.basicConfig(level=logging.DEBUG)


def run_servers(mux, *servers):
    # Count the number of times nothing has been emitted
    c = 0
    while c < 2:
        for s in servers:
            s.process_sockets()
        if mux.unblocked_data_outstanding():
            c = 0
        else:
            c += 1


def make_mux():
    mux = socks.Mux()

    def _make_server_socket(host, port):
        s = socks.FakeSocket(mux)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        s.setblocking(False)
        s.listen(5)
        return s

    def _make_client_socket(host, port, record=False):
        s = socks.FakeSocket(mux)
        s.setblocking(False)
        try:
            s.connect((host, port))
        except BlockingIOError:
            pass
        if record:
            s.text = []
            s.on_receipt = lambda c, p: c.text.append(p.decode('utf-8').rstrip())
        return s

    def _make_selector():
        return socks.Selector(mux)

    return mux, _make_server_socket, _make_client_socket, _make_selector

def test_basic_server():
    mux, mss, mcs, sel = make_mux()

    s = talker.server.Server(make_server_socket=mss,
                             make_client_socket=mcs,
                             selector=sel,
                             host='0.0.0.0',
                             port=8889)

    c = mcs('0.0.0.0', 8889, record=True)

    run_servers(mux, s)

    LOG.debug('fd map: %s', mux.fd_map)
    c.send(b'/nick jan\r\n')
    c.send(b'/who\r\n')

    run_servers(mux, s)

    assert c.text[-2:] == [
        'There are 1 users online:',
        'jan',
    ]
