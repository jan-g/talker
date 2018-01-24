import logging

import talker.server
from .test_utils import run_servers, make_mux

LOG = logging.getLogger(__name__)


def setup_module():
    logging.basicConfig(level=logging.DEBUG)


def test_basic_server():
    mux, mss, mcs, sel = make_mux()

    s = talker.server.Server(make_server_socket=mss,
                             make_client_socket=mcs,
                             selector=sel,
                             host='0.0.0.0',
                             port=8889)

    c = mcs('0.0.0.0', 8889, record=True, send_str=True)

    run_servers(mux, s)  # Give the connection a chance to establish

    LOG.debug('fd map: %s', mux.fd_map)
    c.send('/nick jan\r\n')
    c.send('/who\r\n')

    run_servers(mux, s)  # Gather results of the commands

    assert c.text[-2:] == [
        'There are 1 users online:',
        'jan',
    ]
