import logging

import talker.server


def hello():
    print("Hello from talker-server")


def server():
    # Code goes here
    logging.basicConfig(level=logging.DEBUG)

    s = talker.server.Server()
    s.loop()


if __name__ == '__main__':
    hello()
