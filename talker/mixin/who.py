import talker.mesh
from talker.distributed import LOG, ScatterGatherMixin


class WhoMixin:
    def __init__(self, *args, **kwargs):
        print(self.__class__.__mro__)
        super().__init__(*args, **kwargs)
        self.register_command("/who", WhoMixin.command_who)

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


class WhoObserver(talker.mesh.PeerObserver, ScatterGatherMixin):
    WHO_REQ = 'who'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.register_method(WhoObserver.WHO_REQ, self.recv_who)

    @ScatterGatherMixin.recv_scatter
    def recv_who(self, payload, respond):
        LOG.debug('Who request from %s (%d): %s', respond.source, respond.message_id, payload)
        result = ';'.join(client.name for client in self.server.list_speakers())
        respond(result)

    def who(self, client):
        @self.scatter_request(WhoObserver.WHO_REQ)
        def callback(responses, complete=True):
            LOG.debug('Who responses are all in: %s', responses)
            client.result_who({server: responses[server].split(';') if responses[server] != '' else []
                               for server in responses})
