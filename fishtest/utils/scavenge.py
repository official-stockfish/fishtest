#!/usr/bin/python
import os, sys
from datetime import datetime, timedelta

# For tasks
sys.path.append(os.path.expanduser('~/fishtest/fishtest'))
from fishtest.rundb import RunDb

def scavenge_tasks(scavenge=True, minutes=5):
  """Check for tasks that have not been updated recently"""
  rundb = RunDb()
  for run in rundb.runs.find({'tasks': {'$elemMatch': {'active': True}}}):
    changed = False
    for idx, task in enumerate(run['tasks']):
      if task['active'] and task['last_updated'] < datetime.utcnow() - timedelta(minutes=minutes):
        print 'Scavenging', task
        task['active'] = False
        rundb.clopdb.stop_games(str(run['_id']), idx)
        changed = True
    if changed and scavenge:
      rundb.runs.save(run)

def main():
  scavenge_tasks(scavenge=True)

if __name__ == '__main__':
  main()
