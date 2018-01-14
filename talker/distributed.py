"""
Add some additional distributed capabilities

We add a new version of the /who command that broadcasts a request,
collects responses, and then runs a callback function to process them
when all answers are in.
"""

import logging
import time

import talker.mesh

LOG = logging.getLogger(__name__)


class WhoClient(talker.mesh.SpeakerClient):
    def command_who(self):
        helper = self.server.observer(WhoObserver)
        helper.who(self)

    def result_who(self, responses):
        LOG.debug('result_who: %s', responses)
        count = sum(len(r) for r in responses.values())
        self.output_line('There are {} users online on {} servers:'.format(count, len(responses)))
        for server in sorted(responses):
            self.output_line('  Server: {}'.format(server))
            for speaker in sorted(responses[server]):
                self.output_line('    {}'.format(speaker))

    COMMANDS = dict(talker.mesh.SpeakerClient.COMMANDS)
    COMMANDS.update({
        '/who': command_who,
    })


def speaker_server(**kwargs):
    s = talker.mesh.Server(client_factory=WhoClient, **kwargs)
    s.observe_broadcast(talker.mesh.SpeechObserver(s))
    s.observe_broadcast(talker.mesh.TopologyObserver(s))
    s.observe_broadcast(ScatterGatherObserver(s))
    s.observe_broadcast(WhoObserver(s))
    return s


# This is a more sophisticated observer.
# It can broadcast requests and handle their eventual responses.

class ScatterGatherObserver(talker.mesh.PeerObserver):
    CALLBACK_CACHE_EXPIRY = 1

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.request_id = 0
        self.outstanding_requests = [{}, {}]
        self.last_rotation = time.time()

    def scatter_request(self, message, target=None, callback=None):
        # Give this request an id
        self.request_id += 1
        self.outstanding_requests[0][self.request_id] = ({}, callback)
        self.server.peer_broadcast('{}|{}|{}'.format(self.prefix(), self.request_id, message), target=target)

    def notify(self, peer, source, id, message):
        LOG.debug('Scatter-gather response %d received from %s: %s', id, source, message)
        destination, response_id, payload = message.split('|', 2)
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
                if set(responses) == self.server.observer(talker.mesh.TopologyObserver).reachable():
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
        self.rollover()

    @staticmethod
    def parse_scatter_gather(source, id, message):
        target, request_id, payload = message.split('|', 2)

        def responder(server, result):
            server.peer_broadcast('{}|{}|{}|{}'.format(target, source, request_id, result))

        return responder, payload


class WhoObserver(talker.mesh.PeerObserver):
    def notify(self, peer, source, id, message):
        LOG.debug('Who request from %s (%d): %s', source, id, message)
        respond, payload = ScatterGatherObserver.parse_scatter_gather(source, id, message)

        result = ';'.join(client.name for client in self.server.list_speakers())
        respond(self.server, result)

    def who(self, client):
        def callback(responses, complete=True):
            LOG.debug('Who responses are all in: %s', responses)
            client.result_who({server: responses[server].split(';') if responses[server] != '' else []
                               for server in responses})

        self.server.observer(ScatterGatherObserver).scatter_request('', target=self, callback=callback)