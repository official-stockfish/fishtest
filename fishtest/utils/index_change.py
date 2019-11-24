
# index_change.py - drop/create indexes
#
# Run this script manually to adjust indexes, it could take a few seconds/minutes
# to run.
#
# Ad-hoc changes can be made by adding / commenting out lines as appropriate

from __future__ import print_function

import os
import sys
import pprint
from pymongo import MongoClient, ASCENDING, DESCENDING


db_name='fishtest_new'

# MongoDB server is assumed to be on the same machine, if not user should use
# ssh with port forwarding to access the remote host.
conn = MongoClient(os.getenv('FISHTEST_HOST') or 'localhost')
db = conn[db_name]
runs = db['runs']
pgns = db['pgns']



def printout(s):
  print(s)
  sys.stdout.flush()



# Drop indexes
# printout("\nDropping index ...")
# runs.drop_index('tasks.pending_1')


# Create indexes:

#printout("Creating tasks.pending index ...")
#runs.create_index([('tasks.pending', ASCENDING)])

#printout("Creating pgn index ...")
#pgns.ensure_index([('run_id', ASCENDING)])

printout("Creating tasks.active index ...")
runs.ensure_index([('tasks.active', ASCENDING)])


# Display current list of indexes
printout("\nCurrent indexes on runs:")
pprint.pprint(runs.index_information(), stream=None, indent=1, width=80, depth=None)

#printout("\nCurrent indexes on pgns:")
#pprint.pprint(pgns.index_information(), stream=None, indent=1, width=80, depth=None)
