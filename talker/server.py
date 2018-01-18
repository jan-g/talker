import logging
import talker.base

LOG = logging.getLogger(__name__)


class Client(talker.base.LineBuffered):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.commands = {}
        self.register_command("/help", Client.command_help)
        self.register_command("/quit", Client.command_quit)
        self.register_command("/who", Client.command_who)
        self.register_command("/nick", Client.command_nick)
        self.register_command("/tell", Client.command_tell)
        self.register_command("/kill", Client.command_kill)

    def register_command(self, prefix, callback):
        self.commands[prefix] = callback

    def handle_new(self):
        LOG.debug("New connection from %s", self.addr)
        self.nick = None
        self.output_line("Welcome, {}".format(self))
        self.server.register_speaker(self)
        self.server.tell_speakers("{} has joined".format(self.name))

    def handle_close(self):
        LOG.debug("Connection %s closed", self)
        self.server.unregister_speaker(self)
        self.server.tell_speakers("{} has left".format(self.name))

    def handle_line(self, line):
        """Handle a line of input. It'll be in string form"""
        LOG.debug("Received line of input from client %s: %s", self, line)

        # handle /-commands
        if line.startswith("/"):

            args = line.split()
            if args[0] in self.commands:
                try:
                    self.commands[args[0]](self, *args[1:])
                except Exception as e:
                    LOG.exception("Problem executing command %s", args[0])
                    self.output_line("Something went wrong trying to do that: {}".format(e))
            else:
                self.output_line("Unknown command: {}".format(args[0]))

        else:

            # By default, it's just a line of text
            self.speak(line)

    def speak(self, line):
        self.server.tell_speakers("{}: {}".format(self.name, line))

    @property
    def name(self):
        if self.nick is None:
            return str(self.addr)
        return self.nick

    def matches(self, name):
        return name.lower() == self.name.lower()

    # The following are simple example commands

    def command_quit(self):
        self.close()

    def command_who(self):
        names = sorted([client.name for client in self.server.list_speakers()])
        self.output_line("There are {} users online:".format(len(names)))

        for name in names:
            self.output_line(str(name))

    def command_nick(self, nick):
        # Don't bother with any security for the moment - let people be who they want to be
        if not nick.isalnum():
            self.output_line("You must give an alphanumeric nickname")
            return

        old_name = self.name
        self.nick = nick
        self.server.tell_speakers("{} renames themself as {}".format(old_name, self.nick))

    def command_tell(self, who, *what):
        if len(what) == 0:
            self.output_line("Tell who, what?")
            return

        # locate everyone with that name
        self.server.tell_speakers("{} whispers: {}".format(self.name, " ".join(what)),
                                  include={s for s in self.server.list_speakers()
                                           if s.matches(who)})

    def command_kill(self, who):
        for client in self.server.list_speakers():
            if client.matches(who):
                client.close()

    def command_help(self):
        self.output_line("There are {} commands".format(len(self.COMMANDS)))
        for c in self.COMMANDS:
            self.output_line("  {}".format(c))


class Server(talker.base.Server):
    def __init__(self, client_factory=Client, **kwargs):
        super().__init__(client_factory=client_factory, **kwargs)
        self.speakers = set()

    def register_speaker(self, client):
        self.speakers.add(client)

    def unregister_speaker(self, client):
        self.speakers.remove(client)

    def list_speakers(self):
        return set(self.speakers)

    def tell_speakers(self, message, include=None, exclude=set()):
        if include is None:
            include = self.speakers

        for target in include:
            if target not in exclude:
                target.output_line(message)
