# create_indexes.py - (re-)create indexes
#
# Run this script manually to create the indexes, it could take a few
# seconds/minutes to run.

import os
import sys
import pprint
from pymongo import MongoClient, ASCENDING, DESCENDING


db_name = 'fishtest_new'

# MongoDB server is assumed to be on the same machine, if not user should use
# ssh with port forwarding to access the remote host.
conn = MongoClient(os.getenv('FISHTEST_HOST') or 'localhost')
db = conn[db_name]


def create_runs_indexes():
  db['runs'].create_index(
    [('last_updated', ASCENDING)],
    name='unfinished_runs',
    partialFilterExpression={ 'finished': False }
  )
  db['runs'].create_index(
    [('last_updated', DESCENDING)],
    name='finished_runs',
    partialFilterExpression={ 'finished': True }
  )
  db['runs'].create_index(
    [('last_updated', DESCENDING), ('is_green', DESCENDING)],
    name='finished_green_runs',
    partialFilterExpression={ 'finished': True, 'is_green': True }
  )
  db['runs'].create_index(
    [('last_updated', DESCENDING), ('is_yellow', DESCENDING)],
    name='finished_yellow_runs',
    partialFilterExpression={ 'finished': True, 'is_yellow': True }
  )
  db['runs'].create_index(
    [('last_updated', DESCENDING), ('tc_base', DESCENDING)],
    name='finished_ltc_runs',
    partialFilterExpression={ 'finished': True, 'tc_base': { '$gte': 40 } }
  )
  db['runs'].create_index(
    [('args.username', DESCENDING), ('last_updated', DESCENDING)],
    name='user_runs'
  )

def create_pgn_indexes():
  db['pgns'].create_index([('run_id', DESCENDING)])

def create_users_indexes():
  db['users'].create_index('username', unique=True)

def create_actions_indexes():
  db['actions'].create_index([
    ('username', ASCENDING),
    ('_id', DESCENDING),
  ])

  db['actions'].create_index([
    ('action', ASCENDING),
    ('_id', DESCENDING),
  ])


collection_names = ['users', 'actions', 'runs', 'pgns'] # db.collection_names()

# Loop through all collections and recreate indexes if given in index_list
for collection_name in collection_names:
  c = db[collection_name]

  # Drop all indexes on collections cn except _id_
  index_keys = c.index_information().keys()
  print("Dropping indexes on {} - {}".format(collection_name, index_keys))
  for idx in index_keys:
    if idx != "_id_":
      print("Dropping " + collection_name + " index " + idx + " ...")
      c.drop_index(idx)

print("\nCreating indexes...")
create_users_indexes()
create_actions_indexes()
create_runs_indexes()
create_pgn_indexes()
print("Finished creating indexes!\n")

# Display current list of indexes
for collection_name in collection_names:
  c = db[collection_name]
  print("Current indexes on " + collection_name + ":")
  pprint.pprint(c.index_information(), stream=None, indent=2, width=110, depth=None)
  print("")
