import logging

import talker.mesh


def hello():
    print("Hello from talker-server")


def server():
    # Code goes here
    logging.basicConfig(level=logging.DEBUG)

    s = talker.mesh.Server()
    s.loop()


if __name__ == '__main__':
    hello()
