"""
Add an authentication database, together with a client that makes
state-transitions on login.

Because this uses the Observer mechanism, we will require a Server that
extends talker.mesh.Server
"""

import logging

import talker.mesh
import talker.distributed

LOG = logging.getLogger(__name__)


class LoginMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._main_handler = self.handle_line
        self.handle_line = self._username

    def handle_new(self):
        LOG.debug("New connection from %s", self.addr)
        self.nick = None
        self.output_line("Enter your username, {}:".format(self))

    def _ignore(self, line):
        """Do nothing whilst we wait for a callback."""
        pass

    def _username(self, line):
        user = line.strip()
        if not user.isalpha():
            self.output_line("Usernames must be alphanumeric. Try again:")
            return

        self.nick = user
        self.handle_line = self._ignore
        self.server.observer(LoginObserver).check_user()

        self.server.register_speaker(self)
        self.server.tell_speakers("{} has joined".format(self.name))


class LoginObserver(talker.mesh.PeerObserver):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.load_account_db()

    def load_account_db(self):
        self.account_db = {}

    def notify(self, peer, source, id, message):
        LOG.debug('Who request from %s (%d): %s', source, id, message)
        respond, payload = talker.distributed.ScatterGatherObserver.parse_scatter_gather(source, id, message)

        result = ';'.join(client.name for client in self.server.list_speakers())
        respond(self.server, result)

    def check_user(self, username, callback):
        def callback(responses, complete=True):
            LOG.debug('check_user responses are all in: %s', responses)
            for responder in responses:
                timestamp, username, password = responses[responder].split(';', 2)
            client.result_who({server: responses[server].split(';') if responses[server] != '' else []
                               for server in responses})

        self.server.observer(ScatterGatherObserver).scatter_request('', target=self, callback=callback)