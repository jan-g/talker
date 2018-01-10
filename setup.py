import os.path
from setuptools import setup, find_packages


def read_file(fn):
    with open(os.path.join(os.path.dirname(__file__), fn)) as f:
        return f.read()

setup(
    name="talker",
    version="0.0.1",
    description="Simple text talker server and client",
    long_description=read_file("README.md"),
    author="Jan G",
    author_email="",
    license=read_file("LICENCE.md"),

    packages=find_packages(),

    entry_points={
        'console_scripts': [
            'talker-test = talker.cmd.server:hello',
            'talker-server = talker.cmd.server:server',
        ],
    },

    install_requires=[
                     ],
    tests_require=[
                    "tox",
                    "pytest",
                    "flake8",
                  ],
)
