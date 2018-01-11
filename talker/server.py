import logging
import talker.base

LOG = logging.getLogger(__name__)


class Client(talker.base.LineBuffered):

    def handle_new(self):
        LOG.debug("New connection from %s", self.addr)
        self.output_line("Welcome, {}".format(self.addr))
        self.server.register_speaker(self)
        self.server.tell_speakers("{} has joined".format(self.addr))

    def handle_close(self):
        self.server.unregister_speaker(self)
        self.server.tell_speakers("{} has left".format(self.addr))

    def handle_line(self, line):
        """Handle a line of input. It'll be in string form"""
        LOG.debug("Received line of input from client %s: %s", self.addr, line)

        # handle /-commands
        if line.startswith("/"):

            args = line.split()
            if args[0] in COMMANDS:
                COMMANDS[args[0]](self, args)
            else:
                self.output_line("Unknown command: {}".format(args[0]))

        else:

            # By default, it's just a line of text
            self.server.tell_speakers("{}: {}".format(self.addr, line))


class Server(talker.base.Server):
    def __init__(self, client_factory=Client, **kwargs):
        super().__init__(client_factory=client_factory, **kwargs)
        self.speakers = set()

    def register_speaker(self, client):
        self.speakers.add(client)

    def unregister_speaker(self, client):
        self.speakers.remove(client)

    def tell_speakers(self, message, include=None, exclude=set()):
        if include is None:
            include = self.speakers

        for target in include:
            if target not in exclude:
                target.output_line(message)


# Commands
def quit(client, args):
    client.close()


COMMANDS = {
    "/quit": quit,
}