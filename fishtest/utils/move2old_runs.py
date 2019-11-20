#!/usr/bin/env python

from __future__ import print_function

import os
import sys
from datetime import datetime, timedelta

# For tasks
sys.path.append(os.path.expanduser('~/fishtest/fishtest'))
from fishtest.rundb import RunDb

rundb = RunDb()

def move_tasks(move=True, days=100):
  """Check for tasks to move"""
  skipped = 0
  moved = 0
  for run in rundb.runs.find({'finished': True}):
    if run['last_updated'] < datetime.utcnow() - timedelta(days=days):
        if moved % 100 == 0:
            print('Moved: ', moved, run['last_updated'])
        moved += 1
        if move:
            rundb.old_runs.save(run)
            rundb.runs.remove({'_id': run['_id']})
    else:
        if skipped % 100 == 0:
            print('Skipped: ', skipped, run['last_updated'])
        skipped += 1

def main():
  move_tasks(move=True)

if __name__ == '__main__':
  main()
