import socket
import unittest

import talker.base
import fake_selectors.faux as socks


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

    s = talker.base.Server(make_server_socket=_make_server_socket,
                           make_client_socket=_make_client_socket,
                           selector=socks.Selector)
    s.process_sockets()
