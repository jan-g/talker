import argparse
import logging

import talker.mesh
import talker.server


def hello():
    print("Hello from talker-server")


def server():
    logging.basicConfig(level=logging.DEBUG)

    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8889)
    parser.add_argument('--id')

    args = parser.parse_args()

    s = talker.mesh.speaker_server(port=args.port, peer_id=args.id)

    s.loop()


def simple_server():
    logging.basicConfig(level=logging.DEBUG)

    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8889)

    args = parser.parse_args()

    # Construct a simple server with no peer-to-peer facilities
    s = talker.server.Server(port=args.port)

    s.loop()


if __name__ == '__main__':
    hello()
