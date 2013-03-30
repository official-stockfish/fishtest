### Overview

Fishtest is a distributed task queue for testing chess engines.  It is currently
being used for testing changes on Stockfish with tens of thousands of games per
change, both on Linux and Windows.  The following setup describes a step-by-step
installation for a machine that will run test matches (a worker).

#### Setup Python on Windows

On Windows you will need to install Python 2.7.x for x86 (not 3.x series and not
64 bit) from

http://www.python.org/download/releases/2.7.3/

In case something is not clear please read windows-step-by-step-installation.txt

#### Setup fishtest

You can download fishtest as a zipball directly from https://github.com/glinscott/fishtest
or, in case you have a git installation, you can clone it.

```
git clone https://github.com/glinscott/fishtest.git
```

#### Get username/password

Please e-mail us, and we will give you your username and password.

### Launching the worker

To launch the worker open a console window in *fishtest/worker* directory and run
the following command (after changing *concurrency* to the correct value for
your system, see below), providing username and password you've been given.

```
python worker.py --concurrency 3 username password
```

Option *concurrency* refers to the number of available cores in your system (not
including Hyperthreaded cores!), leaving one core for the OS.  For example,
on my 4 core machine, I use `--concurrency 3`.

On Linux, you can use the `nohup` command to run the worker as a background task.

```
nohup python worker.py --concurrency 3 username password &
```

#### Override default make command

Once launched, fishtest will automatically connect to host, download the book,
the cutechess-cli game manager and the engine sources that will be compiled
according to the type of worker platform. If default make command is not suitable
for you, for instance if you need to use some other compiler than gcc/mingw,
then you can create a `custom_make.txt` file in *fishtest/worker* directory,
containing a single line command that fishtest will run to compile the sources.

### Running the website

This is only if you wish to run your own testing environment (ie. you are testing
changes on another engine). As a pre-requisite, the website needs a mongodb instance.
By default it assumes there is one running on localhost.  You can set FISHTEST_HOST
environment variable to connect to a different host. To launch a development version
of the site, open a console window in *fishtest/fishtest* directory and do:

```
sudo python setup.py develop
./start.sh
```
