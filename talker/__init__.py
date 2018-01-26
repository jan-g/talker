from talker.server import Client
from talker.mesh import Server
from talker.mixin.speech import SpeechObserver, SpeakerMixin
from talker.mixin.topo import TopoMixin, TopologyObserver
from talker.mixin.who import WhoMixin, WhoObserver
from talker.mixin.auth import LoginMixin, LoginObserver


class DistributedClient(WhoMixin, TopoMixin, SpeakerMixin, Client):
    pass

class DistributedAuthClient(LoginMixin, DistributedClient):
    pass

def speaker_server(**kwargs):
    s = Server(client_factory=DistributedClient, **kwargs)
    s.observe_broadcast(SpeechObserver(s))
    s.observe_broadcast(TopologyObserver(s))
    s.observe_broadcast(WhoObserver(s))
    s.observe_broadcast(LoginObserver(s))
    return s
