"""
Add an authentication database, together with a client that makes
state-transitions on login.

Because this uses the Observer mechanism, we will require a Server that
extends talker.mesh.Server
"""

import logging
import time

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
        if not user.isalnum():
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

    def _check_password(self, line):
        if line == self._pw:
            del self._pw
            del self._pw_count
            self._greet()
            return

        # Some problem logging in
        self._pw_count -= 1
        if self._pw_count > 0:
            self.output_line("Enter password:")
            return

        self._reject_with_message("Incorrect password.")

    def _greet(self):
        self.output_line("Welcome, {}".format(self.name))
        self.handle_line = self._main_handler
        self.server.register_speaker(self)
        self.server.tell_speakers("{} has joined".format(self.name))

    def _reject_with_message(self, message):
        self.output_line(message)
        self.handle_line = self._ignore
        self.mark_for_close()

    def _no_username(self, username):
        assert self.nick == username
        self.output_line("A new user! Enter your password:")
        self._un = username
        self.handle_line = self._new_pw

    def _new_pw(self, password):
        self._pw = password
        self.output_line("Confirm your password:")
        self.handle_line = self._confirm_pw

    def _confirm_pw(self, password):
        if self._pw == password:
            self.server.observer(LoginObserver).new_user(self._un, self._pw)
            del self._un
            del self._pw
            self._greet()
            return

        self._reject_with_message("Passwords do not match.")


class LoginObserver(talker.mesh.PeerObserver, talker.distributed.ScatterGatherMixin):
    CHECK_USER = 'check_user'
    NEW_USER = 'new_user'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.load_account_db()
        self.register_method(LoginObserver.CHECK_USER, self.recv_check_user)
        self.register_method(LoginObserver.NEW_USER, self.recv_new_user)

    def load_account_db(self):
        self.account_db = {}

    def check_user(self, client, username):
        @self.scatter_request(LoginObserver.CHECK_USER, username)
        def callback(responses, complete=True):
            LOG.debug('check_user responses are all in: %s', responses)
            ts = pw = None
            for responder in responses:
                if responses[responder] != '':
                    t, u, p = responses[responder].split(';')
                    t = float(t)
                    if ts is None or t > ts and u == username:
                        ts, pw = t, p
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

    def new_user(self, username, password):
        self.broadcast(LoginObserver.NEW_USER, '{};{};{}'.format(time.time(), username, password))

    def recv_new_user(self, peer, source, id, args):
        ts, un, pw = args.split(';', 2)
        ts = float(ts)
        if un not in self.account_db or ts > self.account_db[un][0]:
            self.account_db[un] = (ts, pw)
