
# test_queries.py - run some sample queries to check db speed
#

from __future__ import print_function

import os
import sys
import pprint
import time
from pymongo import MongoClient, ASCENDING, DESCENDING

sys.path.append(os.path.expanduser('~/fishtest/fishtest'))
from fishtest.rundb import RunDb


db_name='fishtest_new'
rundb = RunDb()

# MongoDB server is assumed to be on the same machine, if not user should use
# ssh with port forwarding to access the remote host.
conn = MongoClient(os.getenv('FISHTEST_HOST') or 'localhost')
db = conn[db_name]
runs = db['runs']
pgns = db['pgns']



def printout(s):
  print(s)
  sys.stdout.flush()



printout("\nFetching unfinished runs ...")
start = time.time()
unfinished_runs = rundb.get_unfinished_runs()
end = time.time()

printout(str(end-start) + "s\nFetching machines ...")
start = time.time()
machines = rundb.get_machines()
end = time.time()

printout(str(end-start) + "s\nFetching finished runs ...")
start = time.time()
finished, num_finished = rundb.get_finished_runs(skip=0, limit=50, username='',
                                                 success_only=False, ltc_only=False)
end = time.time()

printout(str(end-start) + "s\nRequesting pgn ...")
if (len(finished) == 0):
    finished.append({'_id':'abc'})
start = time.time()
pgn = rundb.get_pgn(str(finished[0]['_id']) + ".pgn")
end = time.time()

printout(str(end-start) + "s\n")

