"""
Add some additional distributed capabilities

We add a new version of the /who command that broadcasts a request,
collects responses, and then runs a callback function to process them
when all answers are in.
"""

import functools
import logging
import time

import talker.mixin.topo

LOG = logging.getLogger(__name__)


# This is a more sophisticated observer.
# It can broadcast requests and handle their eventual responses.

class ScatterGatherMixin:
    CALLBACK_CACHE_EXPIRY = 1
    GATHER = 'ScatterGatherMixin.gather'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.request_id = 0
        self.outstanding_requests = [{}, {}]
        self.last_rotation = time.time()
        self.register_method(ScatterGatherMixin.GATHER, self.recv_gather)

    def scatter_request(self, method, payload='', callback=None):
        # Is this being used as a decorator?
        if callback is None:
            def wrapper(callback):
                self.request_id += 1
                self.outstanding_requests[0][self.request_id] = ({}, callback)
                self.broadcast(method, '{}|{}'.format(self.request_id, payload))
                return callback
            return wrapper

        # Give this request an id
        self.request_id += 1
        self.outstanding_requests[0][self.request_id] = ({}, callback)
        self.broadcast(method, '{}|{}'.format(self.request_id, payload))

    def recv_gather(self, peer, source, id, payload):
        LOG.debug('Scatter-gather response %d received from %s: %s', id, source, payload)
        destination, response_id, payload = payload.split('|', 2)
        if destination != self.server.peer_id:
            LOG.debug('  this message is not for us, ignoring')
            return

        response_id = int(response_id)

        try:
            for outstanding in self.outstanding_requests:
                if response_id not in outstanding:
                    LOG.info('Dropping incoming response to %d from %s (%d): %s', response_id, source, id, payload)
                    continue

                responses, callback = outstanding[response_id]
                if source in responses:
                    LOG.info('Dropping duplicate response to %d from %s (%d): %s', response_id, source, id, payload)
                    return

                responses[source] = payload
                if set(responses) == self.server.observer(
                        talker.mixin.topo.TopologyObserver).reachable():
                    LOG.debug('Have complete set of responses to %d, triggering callback', response_id)
                    callback(responses)
                    del outstanding[response_id]
                else:
                    LOG.debug('partial set of responses to %d: %s', response_id, responses)

                return

        finally:
            self.rollover()

    def rollover(self):
        # Whatever happens, let's rotate the set of outstanding callbacks
        now = time.time()
        if now - self.last_rotation >= self.CALLBACK_CACHE_EXPIRY:
            for response_id in self.outstanding_requests[1]:
                responses, callback = self.outstanding_requests[1][response_id]
                LOG.debug('Timing out incomplete response %d with responses %s', response_id, responses)
                callback(responses, complete=False)

            self.outstanding_requests = [{}, self.outstanding_requests[0]]
            self.last_rotation = now

    def tick(self):
        super().tick()
        self.rollover()

    @staticmethod
    def parse_scatter_gather(self, source, message_id, payload):
        request_id, payload = payload.split('|', 2)

        def responder(result=''):
            self.broadcast(ScatterGatherMixin.GATHER, '{}|{}|{}'.format(source, request_id, result))

        return responder, payload

    @staticmethod
    def recv_scatter(fn):
        @functools.wraps(fn)
        def recv(self, peer, source, id, payload):
            respond, payload = ScatterGatherMixin.parse_scatter_gather(self, source, id, payload)
            respond.peer = peer
            respond.source = source
            respond.message_id = id
            fn(self, payload, respond)
        return recv
