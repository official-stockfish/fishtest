import copy
import os
from datetime import datetime
from bson.objectid import ObjectId
from pymongo import MongoClient, ASCENDING, DESCENDING

from clopdb import ClopDb
from userdb import UserDb
from actiondb import ActionDb

import stat_util

class RunDb:
  def __init__(self, db_name='fishtest_new', clop_socket=None):
    # MongoDB server is assumed to be on the same machine, if not user should use
    # ssh with port forwarding to access the remote host.
    self.conn = MongoClient(os.getenv('FISHTEST_HOST') or 'localhost')
    self.db = self.conn[db_name]
    self.userdb = UserDb(self.db)
    self.clopdb = ClopDb(self.db, clop_socket)
    self.actiondb = ActionDb(self.db)
    self.runs = self.db['runs']

    self.chunk_size = 1000

  def build_indices(self):
    self.runs.ensure_index([('finished', ASCENDING), ('last_updated', DESCENDING)])

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
              msg_base='',
              msg_new='',
              base_signature='',
              new_signature='',
              regression_test=False,
              start_time=None,
              sprt=None,
              clop=None,
              username=None,
              tests_repo=None,
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
      'msg_base': msg_base,
      'msg_new': msg_new,
      'base_options': base_options,
      'new_options': new_options,
      'info': info,
      'base_signature': base_signature,
      'new_signature': new_signature,
      'username': username,
      'tests_repo': tests_repo,
      'priority': priority,
    }

    if sprt != None:
      run_args['sprt'] = sprt

    if clop != None:
      run_args['clop'] = clop

    new_run = {
      'args': run_args,
      'start_time': start_time,
      # Will be filled in by tasks, indexed by task-id
      'tasks': self.generate_tasks(num_games),
      # Aggregated results
      'results': { 'wins': 0, 'losses': 0, 'draws': 0 },
      'results_stale': False,
      'finished': False,
      'approved': False,
      'approver': '',
    }

    # Check for an existing approval matching the git commit SHAs
    def get_approval(sha):
      q = { '$or': [{ 'args.resolved_base': sha }, { 'args.resolved_new': sha }], 'approved': True }
      return self.runs.find_one(q)
    base_approval = get_approval(resolved_base)
    new_approval = get_approval(resolved_new)
    if base_approval != None and new_approval != None:
      new_run['approved'] = True
      new_run['approver'] = new_approval['approver']

    return self.runs.insert(new_run)

  def get_machines(self):
    machines = []
    for run in self.runs.find({'tasks': {'$elemMatch': {'active': True}}}):
      for task in run['tasks']:
        if task['active']:
          machine = copy.copy(task['worker_info'])
          machine['last_updated'] = task.get('last_updated', None)
          machine['run'] = run
          machine['nps'] = task.get('nps', 0)
          # TODO(glinscott): Temporary - remove once worker version >= 41
          if not isinstance(machine['uname'], basestring):
            machine['uname'] = machine['uname'][0] + machine['uname'][2]
          machines.append(machine)
    return machines

  def get_run(self, id):
    return self.runs.find_one({'_id': ObjectId(id)})

  def get_run_to_build(self):
    return self.runs.find_one({'binaries_url': {'$exists': False}, 'finished': False, 'deleted': {'$exists': False}})

  def get_runs(self):
    return list(self.runs.find(sort=[('last_updated', DESCENDING), ('start_time', DESCENDING)]))

  def get_unfinished_runs(self):
    return self.runs.find({'finished': False},
                          sort=[('last_updated', DESCENDING), ('start_time', DESCENDING)])

  def get_finished_runs(self, skip=0, limit=0, username=''):
    q = {'finished': True, 'deleted': {'$exists': False}}
    if len(username) > 0:
      q['args.username'] = username

    c = self.runs.find(q, skip=skip, limit=limit, sort=[('last_updated', DESCENDING)])
    return (list(c), c.count())

  def get_clop_exclusion_list(self, minimum):
    exclusion_list = []
    for run in self.runs.find({'args.clop': {'$exists': True}, 'finished': False, 'deleted': {'$exists': False}}):
      available_games = 0
      for game in self.clopdb.get_games(run['_id']):
        if len(game['task_id']) == 0:
          available_games += 1

      if available_games < minimum:
        exclusion_list.append(run['_id'])
    return exclusion_list

  def get_results(self, run):
    if not run['results_stale']:
      return run['results']

    results = { 'wins': 0, 'losses': 0, 'draws': 0, 'crashes': 0, 'time_losses':0 }
    for task in run['tasks']:
      if 'stats' in task:
        stats = task['stats']
        results['wins'] += stats['wins']
        results['losses'] += stats['losses']
        results['draws'] += stats['draws']
        results['crashes'] += stats['crashes']
        results['time_losses'] += stats.get('time_losses', 0)

    if 'sprt' in run['args'] and 'state' in run['args']['sprt']:
      results['sprt'] = run['args']['sprt']['state']

    run['results_stale'] = False
    run['results'] = results
    self.runs.save(run)

    return results

  def request_task(self, worker_info):

    # Build list of CLOP runs that are already almost full
    max_threads = int(worker_info['concurrency'])
    if worker_info['username'] == 'glinscott':
      exclusion_list = self.get_clop_exclusion_list(5 + max_threads)
    else:
      exclusion_list = self.get_clop_exclusion_list(1000000)

    # Does this worker have a task already?  If so, just hand that back
    existing_run = self.runs.find_one({'tasks': {'$elemMatch': {'active': True, 'worker_info': worker_info}}})
    if existing_run != None and existing_run['_id'] not in exclusion_list:
      for task_id, task in enumerate(existing_run['tasks']):
        if task['active'] and task['worker_info'] == worker_info:
          if task['pending']:
            return {'run': existing_run, 'task_id': task_id}
          else:
            # Don't hand back tasks that have been marked as no longer pending
            task['active'] = False
            self.runs.save(existing_run)

    # We need to allocate a new task, but first check we don't have the same
    # machine already running because multiple connections are not allowed.
    remote_addr = worker_info['remote_addr']
    machines = self.get_machines()
    connections = sum([int(m.get('remote_addr','') == remote_addr) for m in machines])

    # Allow a few connections, for multiple computers on same IP
    if connections > 3:
      return {'task_waiting': False}

    # Ok, we get a new task that does not require more threads than available concurrency
    q = {
      'new': True,
      'query': { '$and': [ {'tasks': {'$elemMatch': {'active': False, 'pending': True}}},
                           {'args.threads': { '$lte': max_threads }},
                           {'_id': { '$nin': exclusion_list}},
                           {'approved': True}]},
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

    # Find the task we have just activated: the one with the highest 'last_updated'
    latest_time = datetime.min
    for idx, task in enumerate(run['tasks']):
      if 'last_updated' in task and task['last_updated'] > latest_time:
        latest_time = task['last_updated']
        task_id = idx

    # Lower priority of long running tests
    if task_id > 46 and 'sprt' in run['args'] and run['args']['priority'] == 0:
      run['args']['priority'] = -1
      self.runs.save(run)

    return {'run': run, 'task_id': task_id}

  def update_task(self, run_id, task_id, stats, nps, clop):
    run = self.get_run(run_id)
    if task_id >= len(run['tasks']):
      return {'task_alive': False}

    task = run['tasks'][task_id]
    if not task['active'] or not task['pending']:
      return {'task_alive': False}

    # Guard against incorrect results
    num_games = stats['wins'] + stats['losses'] + stats['draws']
    if 'stats' in task and num_games < task['stats']['wins'] + task['stats']['losses'] + task['stats']['draws']:
      return {'task_alive': False}

    task['stats'] = stats
    task['nps'] = nps
    if num_games >= task['num_games']:
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
      sprt_stats = stat_util.SPRT(self.get_results(run),
                                  elo0=sprt['elo0'],
                                  alpha=sprt['alpha'],
                                  elo1=sprt['elo1'],
                                  beta=sprt['beta'],
                                  drawelo=sprt['drawelo'])
      if sprt_stats['finished']:
        run['args']['sprt']['state'] = sprt_stats['state']
        self.runs.save(run)

        self.stop_run(run_id)

    # Update clop results
    if 'clop' in run['args'] and len(clop['game_id']) > 0:
      self.clopdb.write_result(clop['game_id'], clop['game_result'])
      if not task['active']:
        self.clopdb.stop_games(run_id, task_id)

    return {'task_alive': task['active']}

  def failed_task(self, run_id, task_id):
    run = self.get_run(run_id)
    if task_id >= len(run['tasks']):
      return {'task_alive': False}

    task = run['tasks'][task_id]
    if not task['active'] or not task['pending']:
      return {'task_alive': False}

    # Mark the task as inactive: it will be rescheduled
    task['active'] = False
    self.runs.save(run)

    if 'clop' in run['args']:
      self.clopdb.stop_games(run_id, task_id)

    return {}

  def stop_run(self, run_id):
    run = self.get_run(run_id)
    for idx, task in enumerate(run['tasks']):
      is_active = task['active']
      task['active'] = False
      task['pending'] = False
      if 'stats' not in task and not is_active:
        # Truncate the empty tasks
        del run['tasks'][idx:]
        break
    self.runs.save(run)

    return {}

  def approve_run(self, run_id, approver):
    run = self.get_run(run_id)
    # Can't self approve
    if run['args']['username'] == approver:
      return False

    run['approved'] = True
    run['approver'] = approver
    self.runs.save(run)
    return True
