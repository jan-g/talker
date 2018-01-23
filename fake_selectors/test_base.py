import logging
import socket

import talker.server
import fake_selectors.faux as socks

LOG = logging.getLogger(__name__)


def setup_module():
    logging.basicConfig(level=logging.DEBUG)


def test_basic_server():
    mux = socks.Mux()

    def _make_server_socket(host, port):
        s = socks.FakeSocket(mux)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        s.setblocking(False)
        s.listen(5)
        return s

    def _make_client_socket(host, port):
        s = socks.FakeSocket(mux)
        s.setblocking(False)
        try:
            s.connect((host, port))
        except BlockingIOError:
            pass
        return s

    def _make_selector():
        return socks.Selector(mux)

    s = talker.server.Server(make_server_socket=_make_server_socket,
                             make_client_socket=_make_client_socket,
                             selector=_make_selector,
                             host='0.0.0.0',
                             port=8889)

    c = _make_client_socket('0.0.0.0', 8889)
    c.incoming_limit = 0

    while mux.unblocked_data_outstanding():
        LOG.debug('Looping through process_sockets')
        s.process_sockets()  # Handle any reads / accepts
        s.process_sockets()  # Ensure any data is flushed through from corresponding writes

    LOG.debug('fd map: %s', mux.fd_map)

    c.send(b'/who\r\n')

    while mux.unblocked_data_outstanding():
        LOG.debug('Looping through process_sockets')
        s.process_sockets()  # Handle any reads / accepts
        s.process_sockets()  # Ensure any data is flushed through from corresponding writes

    c.incoming_limit = None
    while len(c.incoming_pipe) > 0:
        print(c.recv(16384))
