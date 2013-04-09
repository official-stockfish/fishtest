import copy
import os
from datetime import datetime
from bson.objectid import ObjectId
from pymongo import MongoClient, ASCENDING, DESCENDING

from userdb import UserDb

import stat_util

class RunDb:
  def __init__(self, db_name='fishtest_new'):
    # MongoDB server is assumed to be on the same machine, if not user should use
    # ssh with port forwarding to access the remote host.
    self.conn = MongoClient(os.getenv('FISHTEST_HOST') or 'localhost')
    self.db = self.conn[db_name]
    self.userdb = UserDb(self.db)
    self.runs = self.db['runs']

    self.chunk_size = 1000

  def generate_tasks(self, num_games):
    tasks = []
    remaining = num_games
    while remaining > 0:
      task_size = min(self.chunk_size, remaining)
      tasks.append({
        'num_games': task_size,
        'pending': True,
        'active': False,
      })
      remaining -= task_size
    return tasks

  def new_run(self, base_tag, new_tag, num_games, tc, book, book_depth, threads, base_options, new_options,
              info='',
              resolved_base='',
              resolved_new='',
              base_signature='',
              new_signature='',
              regression_test=False,
              start_time=None,
              sprt=None,
              username=None,
              priority=0):
    if start_time == None:
      start_time = datetime.utcnow()

    run_args = {
      'base_tag': base_tag,
      'new_tag': new_tag,
      'num_games': num_games,
      'tc': tc,
      'book': book,
      'book_depth': book_depth,
      'threads': threads,
      'regression_test': regression_test,
      'resolved_base': resolved_base,
      'resolved_new': resolved_new,
      'base_options': base_options,
      'new_options': new_options,
      'info': info,
      'base_signature': base_signature,
      'new_signature': new_signature,
      'username': username,
      'priority': priority,
    }

    if sprt != None:
      run_args['sprt'] = sprt

    id = self.runs.insert({
      'args': run_args,
      'start_time': start_time,
      # Will be filled in by tasks, indexed by task-id
      'tasks': self.generate_tasks(num_games),
      # Aggregated results
      'results': { 'wins': 0, 'losses': 0, 'draws': 0 },
      'results_stale': False,
      'finished': False,
      'binaries_dir': '',
    })

    return id

  def get_machines(self):
    machines = []
    for run in self.runs.find({'tasks': {'$elemMatch': {'active': True}}}):
      for task in run['tasks']:
        if task['active']:
          machine = copy.copy(task['worker_info'])
          machine['last_updated'] = task.get('last_updated', None)
          machine['run'] = run
          machine['nps'] = task.get('nps', 0)
          machines.append(machine)
    return machines

  def get_run(self, id):
    return self.runs.find_one({'_id': ObjectId(id)})

  def get_runs_to_build(self):
    runs = []
    for run in self.runs.find({ 'binaries_dir': '', 'finished': False }):
      runs.append(run)
    return runs

  def get_runs(self, skip=0, limit=0):
    runs = []
    for run in self.runs.find(skip=skip,
                              limit=limit,
                              sort=[('last_updated', DESCENDING), ('start_time', DESCENDING)]):
      runs.append(run)
    return runs

  def get_results(self, run):
    if not run['results_stale']:
      return run['results']

    results = { 'wins': 0, 'losses': 0, 'draws': 0, 'crashes': 0 }
    for task in run['tasks']:
      if 'stats' in task:
        stats = task['stats']
        results['wins'] += stats['wins']
        results['losses'] += stats['losses']
        results['draws'] += stats['draws']
        results['crashes'] += stats['crashes']

    if 'sprt' in run['args'] and 'state' in run['args']['sprt']:
      results['sprt'] = run['args']['sprt']['state']

    run['results_stale'] = False
    run['results'] = results
    self.runs.save(run)

    return results

  def request_task(self, worker_info):
    # Does this worker have a task already?  If so, just hand that back
    existing_run = self.runs.find_one({'tasks': {'$elemMatch': {'active': True, 'worker_info': worker_info}}})
    if existing_run != None:
      for task_id, task in enumerate(existing_run['tasks']):
        if task['active'] and task['worker_info'] == worker_info:
          if task['pending']:
            return {'run': existing_run, 'task_id': task_id}
          else:
            # Don't hand back tasks that have been marked as no longer pending
            task['active'] = False
            self.runs.save(existing_run)

    # TODO Disable possibility to download regression tests for now
    can_do_regression = False

    # Ok, we get a new task that does not require more threads than available concurrency
    max_threads = int(worker_info['concurrency'])
    q = {
      'new': True,
      'query': { '$and': [ {'tasks': {'$elemMatch': {'active': False, 'pending': True}}},
                           {'args.threads': { '$lte': max_threads }}]},
      'sort': [('args.priority', DESCENDING), ('_id', ASCENDING)],
      'update': {
        '$set': {
          'tasks.$.active': True,
          'tasks.$.last_updated': datetime.utcnow(),
          'tasks.$.worker_info': worker_info,
        }
      }
    }

    run = self.runs.find_and_modify(**q)
    if run == None:
      return {'task_waiting': False}

    latest_time = datetime.min
    for idx, task in enumerate(run['tasks']):
      if 'last_updated' in task and task['last_updated'] > latest_time:
        latest_time = task['last_updated']
        task_id = idx

    return {'run': run, 'task_id': task_id}

  def update_task(self, run_id, task_id, stats, nps):
    run = self.get_run(run_id)
    if task_id >= len(run['tasks']):
      return {'task_alive': False}

    task = run['tasks'][task_id]
    if not task['active']:
      return {'task_alive': False}

    task_alive = task['pending']

    task['stats'] = stats
    task['nps'] = nps
    if stats['wins'] + stats['losses'] + stats['draws'] >= task['num_games']:
      task['active'] = False
      task['pending'] = False

    update_time = datetime.utcnow()
    task['last_updated'] = update_time
    run['last_updated'] = update_time
    run['results_stale'] = True
    self.runs.save(run)

    # Check if SPRT stopping is enabled
    if 'sprt' in run['args']:
      sprt = run['args']['sprt']
      should_stop, state = stat_util.SPRT(self.get_results(run),
                                          elo0=sprt['elo0'],
                                          alpha=sprt['alpha'],
                                          elo1=sprt['elo1'],
                                          beta=sprt['beta'],
                                          drawelo=sprt['drawelo'])
      if should_stop:
        run['args']['sprt']['state'] = state
        self.runs.save(run)

        self.stop_run(run_id)

    return {'task_alive': task_alive}

  def failed_task(self, run_id, task_id):
    run = self.get_run(run_id)
    task = run['tasks'][task_id]
    if not task['active']:
      # TODO: log error?
      return

    # Mark the task as inactive: it will be rescheduled
    task['active'] = False
    self.runs.save(run)

    return {}

  def stop_run(self, run_id):
    run = self.get_run(run_id)
    for idx, task in enumerate(run['tasks']):
      task['pending'] = False
      if 'stats' not in task and not task['active']:
        # Truncate the empty tasks
        del run['tasks'][idx:]
        break
    self.runs.save(run)

    return {}
