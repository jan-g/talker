import logging

import talker

from fake_selectors.test_utils import run_servers, run_servers_randomly, make_mux, clear_client_history, mocked_time
from fake_selectors.test_distributed import construct_network

LOG = logging.getLogger(__name__)


def setup_module():
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger('fake_selectors.faux').setLevel(logging.WARNING)


def test_new_user():
    mux, [server], [client] = construct_network(1, factory = talker.auth_server)

    run_servers(mux, server)
    assert 'Enter your username,'.split() == client.text[0].split()[:3]

    clear_client_history(client)
    client.send('foo\r\n')
    run_servers(mux, server)
    assert ['A new user! Enter your password:'] == client.text

    clear_client_history(client)
    client.send('bar\r\n')
    run_servers(mux, server)
    assert ['Confirm your password:'] == client.text

    clear_client_history(client)
    client.send('bar\r\n')
    run_servers(mux, server)
    assert ['Welcome, foo', 'foo has joined'] == client.text

    clear_client_history(client)
    client.send('hello, world\r\n')
    run_servers(mux, server)
    assert ['foo: hello, world'] == client.text

    # We might build on this test
    return mux, server, client


def test_good_login():
    mux, server, client = test_new_user()
    client.close()
    run_servers(mux, server)

    client = mux._make_client_socket('0.0.0.0', 1000, record=True, send_str = True)
    run_servers(mux, server)
    assert 'Enter your username,'.split() == client.text[0].split()[:3]

    clear_client_history(client)
    client.send('foo\r\n')
    run_servers(mux, server)
    assert ['Enter password:'] == client.text

    clear_client_history(client)
    client.send('bar\r\n')
    run_servers(mux, server)
    assert ['Welcome, foo', 'foo has joined'] == client.text

    clear_client_history(client)
    client.send('hello, world\r\n')
    run_servers(mux, server)
    assert ['foo: hello, world'] == client.text


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger('fake_selectors.faux').setLevel(logging.WARNING)
    test_new_user()
