import argparse
import logging

import talker.mesh


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


if __name__ == '__main__':
    hello()