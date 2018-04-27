#!/usr/bin/python
import os, sys
from datetime import datetime, timedelta

# For tasks
sys.path.append(os.path.expanduser('~/fishtest/fishtest'))
from fishtest.rundb import RunDb

rundb = RunDb()

def scavenge_tasks(scavenge=True, minutes=60):
  """Check for tasks that have not been updated recently"""
  for run in rundb.runs.find({'tasks': {'$elemMatch': {'active': True}}}):
    changed = False
    for idx, task in enumerate(run['tasks']):
      if task['active'] and task['last_updated'] < datetime.utcnow() - timedelta(minutes=minutes):
        print 'Scavenging', task
        task['active'] = False
        changed = True
    if changed and scavenge:
      rundb.runs.save(run)

def get_idle_users(days):
  """Check for users that have never been active"""
  idle = {}
  for u in rundb.userdb.get_users():
      if not 'registration_time' in u \
         or u['registration_time'] < datetime.utcnow() - timedelta(days=days):
        idle[u['username']] = u
  for u in rundb.userdb.user_cache.find():
    if u['username'] in idle:
      del idle[u['username']]
  idle= idle.values()
  return idle

def scavenge_users(scavenge=True, days=28):
    for u in get_idle_users(days):
      if scavenge:
        rundb.userdb.users.remove({'_id': u['_id']})

def main():
  scavenge_tasks(scavenge=True)
  scavenge_users(scavenge=True)

if __name__ == '__main__':
  main()
