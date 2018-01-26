"""
Add an authentication database, together with a client that makes
state-transitions on login.

Because this uses the Observer mechanism, we will require a Server that
extends talker.mesh.Server
"""

import logging

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
        self.server.observer(LoginObserver).check_user(self, user)

    def _have_username(self, username, password):
        assert self.nick == username

        self._pw = password
        self._pw_count = 3
        self.output_line("Enter password:")
        self.handle_line = self._check_password

    def _no_username(self, username):
        assert self.nick == username
        self.output_line("No such user.")

    def _check_password(self, line):
        if line == self._pw:
            self.output_line("Welcome, {}".format(self.name))
            self.handle_line = self._main_handler
            del self._pw
            del self._pw_count
            self.server.register_speaker(self)
            self.server.tell_speakers("{} has joined".format(self.name))


class LoginObserver(talker.mesh.PeerObserver, talker.distributed.ScatterGatherMixin):
    CHECK_USER = 'check_user'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.load_account_db()
        self.register_method(LoginObserver.CHECK_USER, self.recv_check_user)

    def load_account_db(self):
        self.account_db = {}

    def check_user(self, client, username):
        @self.scatter_request(LoginObserver.CHECK_USER, username)
        def callback(responses, complete=True):
            LOG.debug('check_user responses are all in: %s', responses)
            ts = un = pw = None
            for responder in responses:
                if responses[responder] != '':
                    t, u, p = responses[responder].split(';')
                    t = float(t)
                    if ts is None or t > ts and u == username:
                        ts, un, pw = t, u, p
            if ts is not None:
                self.account_db[username] = (ts, pw)
                client._have_username(username, pw)
            else:
                client._no_username(username)

    @talker.distributed.ScatterGatherMixin.recv_scatter
    def recv_check_user(self, username, respond):
        if username in self.account_db:
            ts, pw = self.account_db[username]
            respond('{};{};{}'.format(ts, username, pw))
        else:
            respond()
