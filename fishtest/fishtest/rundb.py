import copy
import os
import random
import time
from datetime import datetime
from bson.objectid import ObjectId
from pymongo import MongoClient, ASCENDING, DESCENDING

from userdb import UserDb
from actiondb import ActionDb
from regressiondb import RegressionDb
from views import parse_tc

import stat_util

class RunDb:
  def __init__(self, db_name='fishtest_new'):
    # MongoDB server is assumed to be on the same machine, if not user should use
    # ssh with port forwarding to access the remote host.
    self.conn = MongoClient(os.getenv('FISHTEST_HOST') or 'localhost')
    self.db = self.conn[db_name]
    self.userdb = UserDb(self.db)
    self.actiondb = ActionDb(self.db)
    self.regressiondb = RegressionDb(self.db)
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
              spsa=None,
              username=None,
              tests_repo=None,
              throughput=1000,
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
      'throughput': throughput,
      'priority': priority,
      'internal_priority': - time.mktime(start_time.timetuple()),
    }

    if sprt != None:
      run_args['sprt'] = sprt

    if spsa != None:
      run_args['spsa'] = spsa

    new_run = {
      'args': run_args,
      'start_time': start_time,
      'last_updated': start_time,
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
    allow_auto = username in ['mcostalba', 'jkiiski', 'glinscott', 'lbraesch'] 
    if base_approval != None and new_approval != None and allow_auto:
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
    return list(self.get_unfinished_runs()) + self.get_finished_runs()[0]

  def get_unfinished_runs(self):
    return self.runs.find({'finished': False},
                          sort=[('last_updated', DESCENDING), ('start_time', DESCENDING)])

  def get_finished_runs(self, skip=0, limit=0, username=''):
    q = {'finished': True, 'deleted': {'$exists': False}}
    if len(username) > 0:
      q['args.username'] = username

    c = self.runs.find(q, skip=skip, limit=limit, sort=[('last_updated', DESCENDING)])
    return (list(c), c.count())

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
    # Check for blocked user or ip
    if self.userdb.is_blocked(worker_info):
      return {'task_waiting': False}

    max_threads = int(worker_info['concurrency'])
    exclusion_list = []

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
    if connections >= self.userdb.get_machine_limit(worker_info['username']):
      return {'task_waiting': False, 'hit_machine_limit': True}

    # Ok, we get a new task that does not require more threads than available concurrency
    q = {
      'new': True,
      'query': { '$and': [ {'tasks': {'$elemMatch': {'active': False, 'pending': True}}},
                           {'args.threads': { '$lte': max_threads }},
                           {'_id': { '$nin': exclusion_list}},
                           {'approved': True}]},
      'sort': [('args.priority', DESCENDING), ('args.internal_priority', DESCENDING), ('_id', ASCENDING)],
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

    # Recalculate internal priority based on task start date and throughput
    # Formula: - second_since_epoch - played_and_allocated_tasks * 3600 * 1000 / games_throughput
    # With default value 'throughput = 1000', this means that the priority is unchanged as long as we play at rate '1000 games / hour'.
    if (run['args']['throughput'] != None and run['args']['throughput'] != 0):
      run['args']['internal_priority'] = - time.mktime(run['start_time'].timetuple()) - task_id * 3600 * 1000 / run['args']['throughput']
    self.runs.save(run)

    return {'run': run, 'task_id': task_id}

  def update_task(self, run_id, task_id, stats, nps, spsa):
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

    # Update spsa results
    if 'spsa' in run['args'] and spsa['wins'] + spsa['losses'] + spsa['draws'] == spsa['num_games']:
      self.update_spsa(run, spsa)

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

    return {}

  def stop_run(self, run_id):
    run = self.get_run(run_id)
    prune_idx = len(run['tasks'])
    for idx, task in enumerate(run['tasks']):
      is_active = task['active']
      task['active'] = False
      task['pending'] = False
      if 'stats' not in task and not is_active:
        prune_idx = min(idx, prune_idx)
      else:
        prune_idx = idx + 1
    # Truncate the empty tasks
    if prune_idx < len(run['tasks']):
      del run['tasks'][prune_idx:]
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

  def request_spsa(self, run_id, task_id):
    run = self.get_run(run_id)

    if task_id >= len(run['tasks']):
      return {'task_alive': False}
    task = run['tasks'][task_id]
    if not task['active'] or not task['pending']:
      return {'task_alive': False}

    result = {
      'task_alive': True,
      'w_params': [],
      'b_params': [],
    }

    spsa = run['args']['spsa']

    # Increment the iter counter
    spsa['iter'] += 1 
    self.runs.save(run)

    # Generate the next set of tuning parameters
    for param in spsa['params']:
      a = param['a'] / (spsa['A'] + spsa['iter']) ** spsa['alpha']
      c = param['c'] / spsa['iter'] ** spsa['gamma']
      R = a / c ** 2
      flip = 1 if bool(random.getrandbits(1)) else -1
      result['w_params'].append({
        'name': param['name'],
        'value': min(max(param['theta'] + c * flip, param['min']), param['max']),
        'R': R,
        'c': c,
        'flip': flip,
      })
      result['b_params'].append({
        'name': param['name'],
        'value': min(max(param['theta'] - c * flip, param['min']), param['max']),
      })
      
    return result

  def update_spsa(self, run, spsa_results):
    spsa = run['args']['spsa']

    spsa['iter'] += int(spsa_results['num_games'] / 2) - 1

    # Update the current theta based on the results from the worker
    # Worker wins/losses are always in terms of w_params
    result = spsa_results['wins'] - spsa_results['losses']
    summary = []
    for idx, param in enumerate(spsa['params']):
      R = spsa_results['w_params'][idx]['R']
      c = spsa_results['w_params'][idx]['c']
      flip = spsa_results['w_params'][idx]['flip']
      param['theta'] = min(max(param['theta'] + R * c * result * flip, param['min']), param['max'])
      summary.append({
        'theta': param['theta'],
        'R': R,
        'c': c,
      })

    # Every 100 iterations, record the parameters
    if 'param_history' not in spsa:
      spsa['param_history'] = []
    if len(spsa['param_history']) < spsa['iter'] / 100:
      spsa['param_history'].append(summary)
