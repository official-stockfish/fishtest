# Overview
Fishtest is a distributed task queue for testing chess engines.  It is currently being used
for testing changes on Stockfish with tens of thousands of games per change.

## Setup

It's recommended to create a new user for running fishtest
```
$ sudo useradd fishtest
$ sudo passwd fishtest
$ su fishtest
$ cd ~
```

### Clone fishtest

You will need the fishtest repository, as well as the development build of Celery.
```
$ git clone https://github.com/glinscott/fishtest.git
$ git clone https://github.com/celery/celery.git
$ cd celery
$ python setup.py build
$ sudo python setup.py install
$ sudo pip install pymongo
```

### Create testing directory

This is where the matches will be run
```
$ cd ~
$ mkdir testing

Edit ~/.bash_profile and add
export FISHTEST_DIR=~/testing

$ cp ~/fishtest/scripts/timed.sh ~/testing
```

Make sure to edit timed.sh to appropriate concurrency!  If you have a 4 core system, it should be -concurrency 3 for example.

Get opening book and cutechess-cli
TODO!

### Set up connection to server

Connect to the server, and forward ports locally (5555 for Celery Flower, 27017 for MongoDB and 5672 for RabbitMQ):

```
$ ssh -v -f username@remote_host -L 5555:localhost:5555 -L 27017:localhost:27017 -L 5672:localhost:5672 -N
```

## Launching the worker

```
$ cd ~/fishtest
$ ./start_worker.sh
```
