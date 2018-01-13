import logging
import talker.base

LOG = logging.getLogger(__name__)


class Client(talker.base.LineBuffered):

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
            if args[0] in self.COMMANDS:
                try:
                    self.COMMANDS[args[0]](self, args)
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

    def command_quit(self, _):
        self.close()

    def command_who(self, _):
        names = sorted([client.name for client in self.server.list_speakers()])
        self.output_line("There are {} users online:".format(len(names)))

        for name in names:
            self.output_line(str(name))

    def command_nick(self, args):
        # Don't bother with any security for the moment - let people be who they want to be
        if not args[1].isalnum():
            self.output_line("You must give an alphanumeric nickname")
            return

        old_name = self.name
        self.nick = args[1]
        self.server.tell_speakers("{} renames themself as {}".format(old_name, self.nick))

    def command_tell(self, args):
        if len(args) < 3:
            self.output_line("Tell who, what?")
            return

        # locate everyone with that name
        who = args[1]
        what = " ".join(args[2:])

        self.server.tell_speakers("{} whispers: {}".format(self.name, what),
                                  include={s for s in self.server.list_speakers()
                                           if s.matches(who)})

    def command_kill(self, args):
        for client in self.server.list_speakers():
            if client.matches(args[1]):
                client.close()

    def command_help(self, args):
        self.output_line("There are {} commands".format(len(self.COMMANDS)))
        for c in self.COMMANDS:
            self.output_line("  {}".format(c))

    COMMANDS = {
        "/help": command_help,
        "/quit": command_quit,
        "/who": command_who,
        "/nick": command_nick,
        "/tell": command_tell,
        "/kill": command_kill,
    }



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
