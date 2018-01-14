# The protocol

The talker uses CRLF-delimited lines as a record. Each line is either just a thing
to say, or some kind of `/`-prefixed command.

It's possible to use `netcat` as a client to generate such input and process the
corresponding responses:

```bash
% nc -c localhost 8889
```

# Multiple servers

As well as standard client sockets, the server also supports peer-to-peer mesh networking.
The client command

    /peer-listen 0.0.0.0 9999

will cause a server to listen on a server-to-server socket at the given address.

A second server can be asked to connect to the first by issuing the client command:

    /peer-connect 0.0.0.0 9999

At that point, the two servers will connect to each other. You can ask a server to give the
details of the other servers it's connected to by using the client command:

    /peers

## Mesh-enabled commands

Most commands are not yet mesh-enabled. The one that is is the standard 'talker' - this
broadcasts anything a client says to all nodes in the network. As the line of speech is
received at a server, it relays it to each connected client.

The mechanism for this is identical whether the server is a singleton or part of a network.
The client broadcasts a notification to the `SpeechObserver` class; this notification floods
the server network. As a `SpeechObserver` receives it, it relays the text to local clients.

```
SpeakerClient  talker.mesh.Server  SpeechObserver  talker.mesh.Server SpeakerClient(s)  talker.mesh.Server  SpeechObserver  talker.mesh.Server  SpeakerClient(s)
(local)        (local)             (local)         (local)            (local)           (remote)            (remote)        (remote)            (remote)
    |              |                   |               |                  |                  |                  |               |                   |
    |              |                   |               |                  |                  |                  |               |                   |
  speak -------> peer_broadcast        |               |                  |                  |                  |               |                   |
    |            notify_observers      |               |                  |                  |                  |               |                   |
    |              |---------------> notify            |                  |                  |                  |               |                   |
    |              |                   |-----------> tell_speakers        |                  |                  |               |                   |
    |              |                   |               |--------------> output_line          |                  |               |                   |
    |              |                   |               |--------------> output_line          |                  |               |                   |
    |              |                   |               |--------------> output_line          |                  |               |                   |
    |              |                   |               |                  |                  |                  |               |                   |
    |            peer_propagate        |               |                  |                  |                  |               |                   |
    |              |------------------ | ------------- | ---------------- | ------------> peer_receive          |               |                   |
    |              |                   |               |                  |               notify_observers      |               |                   |
    |              |                   |               |                  |                  |--------------> notify            |                   |
    |              |                   |               |                  |                  |                  |----------> tell_speakers          |
    |              |                   |               |                  |                  |                  |               |--------------> output_line
    |              |                   |               |                  |                  |                  |               |--------------> output_line
    |              |                   |               |                  |                  |                  |               |--------------> output_line
    |              |                   |               |                  |                  |                  |               |                   |
    |              |                   |               |                  |                  |                  |               |                   |

```

This approach isn't perfect: the knowledge of how to locate 'speakers' is partly built into the
`Server`; ideally, the SpeechObserver would be able to perform this aggregation directly, if the Server grew
an observation mechanism for ordinary client connections.

## Server-to-server communication mechanism

The most basic mechanism of server-to-server communication is a simple, one-way _broadcast_: a server sends
a message to each of its directly connected peers, which in turn forward it to _their_ peers, and so on.
On receipt of a message, local observers are notified of any messages they are interested in. (There's a
mechanism to suppress duplicate notifications arising from messages looping around a peer network that's
not simply-connected.)

This is a great building-block for talkers, since most traffic originating at a client needs to be broadcast
to all other clients.

Additionally, there's a lower-level mechanism for sending a message to one directly-connected peer. This
is used by the topology management.

## Topology management

A second observer handles the local calculation of the network's topology. When a server detects a new
peer connection, it sends an `I-AM` message to its new peer, identifying itself.

Each peer, on receiving such a message, updates its route table to reflect the new connection.

As route table entries are updated, they are broadcast around the mesh network. The `TopologyObserver`
collects these messages and remembers the most recent peer set that each server is connected to.
From this information, it can calculate all the servers that it can reach.
(A consequence of this is that every server has a complete picture of the topology of all reachable
servers, once the algorithm stabilises.)

## More advanced RPC

There are two more advanced forms of RPC that might be necessary. One is a point-to-point unidirectional
message; this can be achieved by broadcasting the message, tagging it with a "for the eyes only of"
attribute.

The second form is a two-way operation: eg, a network-wide `/who` might use this. Rather than attempt to
maintain global tables (which is what the `TopologyObserver` does) - in itself, a perfectly reasonable
approach - we might perform a _scatter-gather_ call. Messages are broadcast to target nodes with a reply
address. As replies come back, they are collated. When we have received replies from all targets, or
at a suitable timeout, the available results are presented to a callback function.

(This would make commands like `/who` effectively asynchronous: the user types the command, and may
issue other commands in the interim; at some point in the future, the server responds with a result.)