# Talker server and client

There's a bunch of stuff in here. The following files are kind of boilerplate:

- LICENSE.md
- README.md
- setup.py
- tox.ini
- .gitignore

I just copy these around to a new directory to start a new Python project.

These are the bits required to make a Python package. Packaging can be of two
kinds: either a system-level package (that you use apt to install) or a Python
package (that uses language-specific tools). The above files are the bits necessary
to manage installation using the Python tools.

## Using a Python "virtual environment"

A python virtualenv is a directory tree containing a stand-alone Python interpreter,
any Python scripts (that is, executable programs) and copies of any Python libraries
required to run those scripts.

If you're working on several different bits of software, one reasonably convenient
approach is to isolate the resulting artifacts into their own virtualenvs rather
than trying to install them using your system Python.

You might need to `apt install virtualenv python3.6` to make the following work:

    % cd
    % virtualenv venv-1 --python=python3.6

This creates a directory tree rooted at `~/venv-1` which contains a Python-3.6
interpreter. (This works for Python 2.7 too.) You can also create virtualenvs from
inside PyCharm - Preferences, find the `Project: foo / Project interpreter` pane;
you can search for `project interpreter` to locate this. There's a drop-down list
of potential environments. Hit the cog icon and `add local`. Pick a location and
an interpreter to base the environment on (I picked python3.6) and it'll configure
PyCharm to use the same directory tree.

The _executable_ files in that virtualenv live under `~/venv-1/bin`. There's a copy
of `python` in there. Additionally, any executable scripts that you declare in your
`setup.py` will be installed there: eg, in `setup.py` there is this stanza:

```python
    entry_points={
        'console_scripts': [
            'talker-test = talker.cmd:hello',
        ],
    },
```

If I use the python packaging tool, `pip`, to install the software:

```sh
# (assuming that ~/talker is where you've checked the source code out to)
% cd ~/talker
% ~/venv-1/bin/pip install -e .
Obtaining file:///home/jang/talker
Installing collected packages: talker
  Running setup.py develop for talker
Successfully installed talker
```

... then it'll create an executable script in `~/venv-1/bin/talker-server` which, when I
run it, will call the `hello` function defined in the `talker/cmd.py` file.
I can run it like this:

```sh
% ~/venv-1/bin/talker-test
Hello from talker-server
```

and it'll automatically use the correct Python virtualenv to look up its libraries in.

### That pip command

The `pip install -e .` means "install the Python package rooted in the current directory
(that's what `.` means)". `-e` means "install in *editable* mode". That creates the scripts
specified by `setup.py` with *dynamic* links back to the current directory tree. Thus, when
you make changes to your software, the `~/venv-1/bin/talker-server` script's behaviour will
be updated to reflect that the next time you run it.

### When to re-run that pip command

You don't need to re-run the `pip` command if you simply create or change the contents
of your program files - although running processes won't pick up any changes without
being restarted, so you might need to kill and restart your server.

You _will_ likely need to re-run the `pip` command if you want to make any changes
in your `setup.py` take effect. These include adding new executable script definitions
and adding any other Pythono libraries to your project.

(There are tools inside PyCharm to help you manage your virtualenv too; they run commands
like this for you.)

### Modifying your PATH

Rather than specifying the path to those scripts each time, you can add a prefix to your
shell's `PATH` variable telling it where to look for executable files:

```sh
% export PATH=~/venv-1/bin:$PATH
```

Now you don't need to explicitly give the path to those executable scripts:

```sh
% talker-test
Hello from talker-server
```

Note: that variable is local to _each shell window_; if you have multiple terminal
windows open, you'll need to give that command in each one. Alternatively you can
edit your `~/.bashrc` to add that line at the bottom; then any _new_ terminals you
open will use that new setting (because they launch new `bash` processes).

### Why bother with all this?

It can be helpful to use the packaging boilerplate for a few reasons. They mostly
come down to a combination of tidyness, repeatability, and documentation: firstly,
the `setup.py` file describes what executables you provide and what Python libraries
your code depends on; you have a more repeatable way to set up Python code if you're
working on a project.

Secondly, it's possible to package up your code into something that `pip` can
fetch (and even publish it) - so you can add to the Python ecosystem.

### The meaning of `if __name__ == 'main':`

You have two ways to launch your code from within PyCharm. One is to use the `terminal`
tool window and just enter the script name in the command-line there. (To make this
work you'll need to use `pip install -e .` first to link up the executable scripts.)
The shell that runs in this window will come with the path to the `bin` directory of
the project's virtualenv pre-configured into it.

The second way is to just right-click on a Python file and choose `Run` from the
drop-down menu. This will invoke the Python interpreter on that file.

However, most Python modules have lots of _definitions_ in them but don't necessarily
do anything when _run directly_.

If you want a Python module to also double as an executable target itself, you can put
something like this at the bottom of the file:

```python
if __name__ == '__main__':
    main()
```

You'll see this at the end of a few Python modules. `__name__` is a special variable
defined by the Python interpreter; its value is set to the string `__main__` iff
the current module is being invoked directly by the Python interpreter (ie, if you
typed `python talker/cmd/server.py` or PyCharm ran the equivalent for you). Otherwise,
such as the case when the module is simply being imported by another piece of Python
code, the variable will be set to the name of the module (`talker.cmd.server`).

The code that you put into that `if` stanza is entirely up to you.

## Python package naming

Inside the Python language, modules have names. These might be multipath names
that are `.`-separated. Those package hierarchies are typically shallow; eg, the
Python standard library has things like `collections`, `os`, and also `os.path`.

Your own software can have similar multi-level packages (if you like). These map
onto file and directory names: for instance, `talker/cmd/server.py` can be imported
from a piece of Python code like this:

```python
import talker.cmd.server
```

It's the responsibility of the `pip` command to assemble all the component packages
into the virtualenv so that they can refer to each other: you'll see a file hierarchy
under `~/venv-1/lib` that mirrors the Python package hierarchy of that virtualenv.

## Testing

Python has some support for writing unit tests. A test is just a function that tries
to do something and checks the result. Tools like `pytest` and `tox` can be used to
automatically scan through a set of directories looking for files and functions that
match a particular set of patterns (usually, that they start with `test`). PyCharm can
also run a test for you dynamically.

### What do I test?

Tests come in various sizes and scope. The smallest are "unit tests". These test things
like an individual function: if I call such a function with a particular input, do I
get the result that I'm looking for?

It's easy to test mathematical functions. Testing things like IO are more complex; it can
help to try to structure your code so that the IO code is as simple as possible and hands
off input to handler functions - you can then test those handler functions by passing
fake input to them.
