# create_indexes.py - (re-)create indexes
#
# Run this script manually to create the indexes, it could take a few
# seconds/minutes to run.
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


index_list = {
  'runs' : [
    [
      # Index used for querying combos of username / Greens / LTC
      ('finished', DESCENDING),
      ('args.username', ASCENDING),
      ('args.tc', ASCENDING),
      ('results_info.style', ASCENDING),
      ('last_updated', DESCENDING),
    ],
    [
      # Index used for get_unfinished_runs()
      ('finished', ASCENDING),
      ('last_updated', DESCENDING),
      ('start_time', DESCENDING),
    ],
    # [(u'deleted', ASCENDING)],
    # [(u'deleted', ASCENDING), (u'finished', ASCENDING)],
    # [(u'last_updated', DESCENDING), (u'start_time', DESCENDING)],
    # [(u'tasks.pending', ASCENDING)],
  ],
  'old_runs' : [
    [
      # Index used for querying combos of username / Greens / LTC only
      ('finished', DESCENDING),
      ('args.username', ASCENDING),
      ('args.tc', ASCENDING),
      ('results_info.style', ASCENDING),
      ('_id', DESCENDING),
    ],
  ],
  'pgns' : [
    [('run_id', ASCENDING)]
  ],
  'users' : [
    [('username', ASCENDING)]
  ],
  'actions' : [
    [
      ('action', ASCENDING),
      ('username', ASCENDING),
      ('_id', DESCENDING)
    ]
  ],
}
unique_list = [ 'username' ]


def printout(s):
  print(s)
  sys.stdout.flush()


# Loop through all collections and recreate indexes if given in index_list
for cn in db.list_collection_names():
  if cn in index_list:
    c = db[cn]

    # Drop all indexes on collections cn except _id_
    printout("")
    for idx in c.index_information().keys():
      if idx != "_id_":
        printout("Dropping " + cn + " index " + idx + " ...")
        c.drop_index(idx)

    # Create indexes in index_list
    printout("")
    for flds in index_list[cn]:
      printout("Creating " + cn + " index " + str(flds) + " ...")
      uniq = False
      if cn != 'actions' and flds[0][0] in unique_list:
          uniq = True
      c.create_index(flds, unique=uniq)


# Display current list of indexes
for cn in db.list_collection_names():
  c = db[cn]
  printout("\nCurrent indexes on " + cn + ":")
  pprint.pprint(c.index_information(), stream=None, indent=2, width=110, depth=None)

printout("")
