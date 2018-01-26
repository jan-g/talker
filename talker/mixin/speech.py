import talker.server
from talker.mesh import PeerObserver

# This causes speech to be broadcast to all connected servers


class SpeakerMixin:
    def speak(self, line):
        self.server.observer(SpeechObserver).send_say(self.name, line)


class SpeechObserver(PeerObserver):
    SAY = 'SAY'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.register_method(SpeechObserver.SAY, self.recv_say)

    def send_say(self, who, what):
        self.broadcast(SpeechObserver.SAY, '{}|{}'.format(who, what))

    def recv_say(self, _, source, id, args):
        name, line = args.split('|', 1)
        self.server.tell_speakers("{}: {}".format(name, line))
