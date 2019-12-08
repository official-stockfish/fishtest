
# create_indexes.py - (re-)create indexes
#
# Run this script manually to create the indexes, it could take a few seconds/minutes
# to run.
#
# If any indexes need to be removed, edit dropList as appropriate.

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


indexList = { 'runs' : [ [(u'args.username', ASCENDING)],
                         [(u'finished', ASCENDING), (u'last_updated', DESCENDING), (u'start_time', DESCENDING)] ],
                         # [(u'finished', ASCENDING), (u'last_updated', DESCENDING)],
                         # [(u'deleted', ASCENDING)],
                         # [(u'deleted', ASCENDING), (u'finished', ASCENDING)],
                         # [(u'last_updated', DESCENDING), (u'start_time', DESCENDING)],
                         # [(u'tasks.pending', ASCENDING)],
              'pgns' : [ [('run_id', ASCENDING)] ],
              'users' : [ [('username', ASCENDING)] ]
            }
uniqueList = [ 'username' ]


def printout(s):
  print(s)
  sys.stdout.flush()


# Loop through all collections and recreate indexes if given in indexList
for cn in db.list_collection_names():
  if cn in indexList:
    c = db[cn]

    # Drop all indexes on collections cn except _id_
    printout("")
    for idx in c.index_information().keys():
      if idx != "_id_":
        printout("Dropping " + cn + " index " + idx + " ...")
        c.drop_index(idx)

    # Create indexes in indexList
    printout("")
    for flds in indexList[cn]:
      printout("Creating " + cn + " index " + str(flds) + " ...")
      uniq = True if flds[0][0] in uniqueList else False
      c.create_index(flds, unique=uniq)


# Display current list of indexes
for cn in db.list_collection_names():
  c = db[cn]
  printout("\nCurrent indexes on " + cn + ":")
  pprint.pprint(c.index_information(), stream=None, indent=2, width=110, depth=None)

printout("")

