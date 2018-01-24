# Testing

Server operation centres on an event loop. This uses Python's `selectors` module to
handle the IO polling. Each time through the loop, any readable sockets are serviced,
and the resulting input is massaged and passed through a stack of ever-higher-level
method calls - first dealing with the incoming packets, then a sequence of bytes,
then a sequence of logical datagrams, then interpreting those as commands, etc.

In order to test the server as a whole we have two options. The first is to actually
run up a listening server, and attach our own `TalkerClient` connection to it. The
complexity here lies largely in interspersing the client commands with the server,
and being able to tell (in a test case) when the system has quiesced.

The second option is to fake up sockets. In order to do this we supply fake implentations
of the `socket` and `Selector` classes. The `Server` class is adjusted so that we can
inject these alternative implementations into it. Some utility functions are supplied
to make running a server (or set of servers) "for a bit" - that is, until nothing else
useful appears to be happening - straightforward.

The `FakeSocket` class also has the ability to block messages from being delivered.
The point of this is to aid in algorithm validation: we can, potentially, explicitly
sequence the messages that are delivered, in order to confirm that any legal operation
of the protocol in a particular situation will converge to teh same set of results.

This doesn't constitute a general proof - rather, it's a testing mechanism. Note, the
exhaustive search through the space of potential message delivery orders is exponentially
explosive; doing this for anything other than small scenarios is likely prohibitively
expensive.

It should be added: this isn't unit testing! Rather, this is a way to fake up a
whole-system integration test to validate specific pieces of functionality.
