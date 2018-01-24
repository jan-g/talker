"""
Actual tests for the behaviour of the faux socket implementation
"""
import logging

from fake_selectors.test_utils import make_mux

LOG = logging.getLogger(__name__)


def setup_module():
    logging.basicConfig(level=logging.DEBUG)


def test_client_misconnect_error():
    mux, mss, mcs, sel = make_mux()

    c = mcs('0.0.0.0', 1001, record=True)
    assert len(c.text) == 1 and isinstance(c.text[0], ConnectionRefusedError)
