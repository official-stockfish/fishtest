import copy
import os
import random
import math
import time
import threading
import zlib
import re

from datetime import datetime, timedelta
from bson.objectid import ObjectId
from bson.binary import Binary
from pymongo import MongoClient, ASCENDING, DESCENDING
from userdb import UserDb
from actiondb import ActionDb
from views import format_results

import fishtest.stat_util

class RunDb:
  def __init__(self, db_name='fishtest_new'):
    # MongoDB server is assumed to be on the same machine, if not user should use
    # ssh with port forwarding to access the remote host.
    self.conn = MongoClient(os.getenv('FISHTEST_HOST') or 'localhost')
    self.db = self.conn[db_name]
    self.userdb = UserDb(self.db)
    self.actiondb = ActionDb(self.db)
    self.pgndb = self.db['pgns']
    self.runs = self.db['runs']
    self.old_runs = self.db['old_runs']
    self.deltas = self.db['deltas']

    self.chunk_size = 250

  def build_indices(self):
    self.runs.ensure_index([('finished', ASCENDING), ('last_updated', DESCENDING)])
    self.pgndb.ensure_index([('run_id', ASCENDING)])

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
              start_time=None,
              sprt=None,
              spsa=None,
              username=None,
              tests_repo=None,
              auto_purge=True,
              throughput=100,
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
      'auto_purge': auto_purge,
      'throughput': throughput,
      'itp': 100,  # internal throughput
      'priority': priority,
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

    return self.runs.insert(new_run)

  def get_machines(self):
    machines = []
    for run in self.runs.find({'finished': False, 'tasks': {'$elemMatch': {'active': True}}}):
      for task in run['tasks']:
        if task['active']:
          machine = copy.copy(task['worker_info'])
          machine['last_updated'] = task.get('last_updated', None)
          machine['run'] = run
          machine['nps'] = task.get('nps', 0)
          machines.append(machine)
    return machines

  def get_pgn(self, id):
    id = id.split('.')[0] # strip .pgn
    pgn = self.pgndb.find_one({'run_id': id})
    if pgn:
      return zlib.decompress(pgn['pgn_zip']).decode()
    return None

  def get_pgn_100(self, skip):
    return [p['run_id'] for p in self.pgndb.find(skip=skip, limit=100, sort=[('_id',DESCENDING)])]

  # Cache runs
  run_cache = {}
  run_cache_lock = threading.Lock()
  run_cache_write_lock = threading.Lock()

  timer = None

  def get_run(self, id):
    with self.run_cache_lock:
      id = str(id)
      if id in self.run_cache:
        self.run_cache[id]['rtime'] = time.time()
        return self.run_cache[id]['run']
      run = self.runs.find_one({'_id': ObjectId(id)})
      if not run:
        run = self.old_runs.find_one({'_id': ObjectId(id)})
      self.run_cache[id] = { 'rtime': time.time(), 'ftime': time.time(), 'run': run, 'dirty': False }
      return run

  def buffer(self, run, flush):
    with self.run_cache_lock:
      if self.timer is None:
        self.timer = threading.Timer(1.0, self.flush_buffers)
        self.timer.start()
      id = str(run['_id'])
      if flush:
        self.run_cache[id] = { 'dirty': False, 'rtime': time.time(), 'ftime': time.time(), 'run': run }
        with self.run_cache_write_lock:
          self.runs.save(run)
      else:
        if id in self.run_cache:
          ftime = self.run_cache[id]['ftime']
        else:
          ftime = time.time()
        self.run_cache[id] = { 'dirty': True, 'rtime': time.time(), 'ftime': ftime, 'run': run }

  def stop(self):
    with self.run_cache_lock:
      self.timer = None
    time.sleep(1.1)

  def flush_buffers(self):
    with self.run_cache_lock:
      if self.timer is None:
        return
      now = time.time()
      old = now + 1
      oldest = None
      for id in self.run_cache.keys():
        if not self.run_cache[id]['dirty']:
          if self.run_cache[id]['rtime'] < now - 60:
            del self.run_cache[id]
        elif self.run_cache[id]['ftime'] < old:
          old = self.run_cache[id]['ftime']
          oldest = id
      if not oldest is None:
        if int(now) % 60 == 0:
          self.scavenge(self.run_cache[oldest]['run'])
        with self.run_cache_write_lock:
          self.runs.save(self.run_cache[oldest]['run'])
        self.run_cache[oldest]['dirty'] = False
        self.run_cache[oldest]['ftime'] = time.time()
      self.timer = threading.Timer(1.0, self.flush_buffers)
      self.timer.start()

  def scavenge(self, run):
    old = datetime.utcnow() - timedelta(minutes=30)
    for task in run['tasks']:
      if task['active'] and task['last_updated'] < old:
        task['active'] = False

  def get_runs(self):
    return list(self.get_unfinished_runs()) + self.get_finished_runs()[0]

  def get_unfinished_runs(self):
    with self.run_cache_write_lock:
      return self.runs.find({'finished': False},
                          sort=[('last_updated', DESCENDING), ('start_time', DESCENDING)])

  def get_finished_runs(self, skip=0, limit=0, username='', success_only=False, ltc_only=False):
    q = {'finished': True}
    if len(username) > 0:
      q['args.username'] = username
    if ltc_only:
      q['args.tc'] = {'$regex':'^([4-9][0-9])|([1-9][0-9][0-9])'}
    if success_only:
      # This is unfortunate, but the only way we have of telling if a run was successful or
      # not currently is the color!
      q['results_info.style'] = '#44EB44'

    c = self.runs.find(q, skip=skip, limit=limit, sort=[('last_updated', DESCENDING)])
    no_del = []
    del_count = 0
    for run in c:
      if 'deleted' in run:
        del_count += 1
        continue
      no_del.append(run)
    result = [no_del, c.count()]

    if limit != 0 and len(result[0]) != limit - del_count:
      c = self.old_runs.find(q, skip=max(0, skip-c.count()),
                             limit=limit-len(result[0]),
                             sort=[('_id',DESCENDING)])
      result[0] += list(c)
      result[1] += c.count()
    else:
      result[1] += self.old_runs.find().count()

    return result

  def get_results(self, run, save_run=True):
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
    if save_run:
      self.buffer(run, True)

    return results

  def calc_itp(self, run):
    itp = run['args']['throughput']
    if itp < 1:
      itp = 1
    elif itp > 500:
      itp = 500
    itp *= math.sqrt(float(run['args']['tc'].split('+')[0]) / 10)
    itp *= math.sqrt(run['args']['threads'])
    if 'sprt' not in run['args']:
      itp *= 0.5
    else:
      results = self.get_results(run)
      run['results_info'] = format_results(results, run)
      if 'llr' in run['results_info']:
        llr = run['results_info']['llr']
        itp *= (5 + llr) / 5
    run['args']['itp'] = itp

  def sum_cores(self, run):
    cores = 0
    for task in run['tasks']:
      if task['active']:
        cores += int(task['worker_info']['concurrency'])
    run['cores'] = cores

  # Limit concurrent request_task
  task_lock = threading.Lock()
  task_semaphore = threading.Semaphore(4)

  task_time = 0
  task_runs = None

  def request_task(self, worker_info):
    if self.task_semaphore.acquire(False):
      try:
        with self.task_lock:
          return self.sync_request_task(worker_info)
      finally:
        self.task_semaphore.release()
    else:
      return {'task_waiting': False}

  def sync_request_task(self, worker_info):
    if time.time() > self.task_time + 60:
      self.task_runs = []
      for r in self.get_unfinished_runs():
        run = self.get_run(r['_id'])
        self.sum_cores(run)
        r['cores'] = run['cores']
        self.calc_itp(run)
        r['args']['itp'] = run['args']['itp']
        self.task_runs.append(r)
      self.task_runs.sort(key=lambda r: (-r['args']['priority'],
        r['cores'] / r['args']['itp'] * 100.0, -r['args']['itp'], r['_id']))
      self.task_time = time.time()

    max_threads = int(worker_info['concurrency'])
    min_threads = int(worker_info.get('min_threads', 1))
    max_memory = int(worker_info.get('max_memory', 0))
    exclusion_list = []

    # We need to allocate a new task, but first check we don't have the same
    # machine already running because multiple connections are not allowed.
    connections = 0
    for run in self.task_runs:
      for task in run['tasks']:
        if task['active'] and task['worker_info']['remote_addr'] == worker_info['remote_addr']:
          connections = connections + 1

    # Allow a few connections, for multiple computers on same IP
    if connections >= self.userdb.get_machine_limit(worker_info['username']):
      return {'task_waiting': False, 'hit_machine_limit': True}

    # Get a new task that matches the worker requirements
    run_found = False
    for runt in self.task_runs:
      run = self.get_run(runt['_id'])
      # compute required TT memory
      need_tt = 0
      if max_memory > 0:
        def get_hash(s):
          h = re.search('Hash=([0-9]+)', s)
          if h:
            return int(h.group(1))
          return 0
        need_tt += get_hash(run['args']['new_options'])
        need_tt += get_hash(run['args']['base_options'])
        need_tt *= max_threads // run['args']['threads']

      if run['_id'] not in exclusion_list and run['approved'] \
         and run['args']['threads'] <= max_threads \
         and run['args']['threads'] >= min_threads \
         and need_tt <= max_memory:
        task_id = -1
        for task in run['tasks']:
          task_id = task_id + 1
          if not task['active'] and task['pending']:
            task['worker_info'] = worker_info
            task['last_updated'] = datetime.utcnow()
            task['active'] = True
            run_found = True
            break
      if run_found:
        break

    if not run_found:
      return {'task_waiting': False}

    for runt in self.task_runs:
      if runt['_id'] == run['_id']:
        self.sum_cores(run)
        runt['cores'] = run['cores']
        self.task_runs.sort(key=lambda r: (-r['args']['priority'],
          r['cores'] / r['args']['itp'] * 100.0, -r['args']['itp'], r['_id']))
        break

    self.buffer(run, False)

    return {'run': run, 'task_id': task_id}

  # Create a lock for each active run
  run_lock = threading.Lock()
  active_runs = {}
  purge_count = 0

  def active_run_lock(self, id):
    with self.run_lock:
      self.purge_count = self.purge_count + 1
      if self.purge_count > 100000:
        old = time.time() - 10000
        self.active_runs = dict((k,v) for k, v in self.active_runs.iteritems() if v['time'] >= old)
        self.purge_count = 0
      if id in self.active_runs:
        active_lock = self.active_runs[id]['lock']
        self.active_runs[id]['time'] = time.time()
      else:
        active_lock = threading.Lock()
        self.active_runs[id] = { 'time': time.time(), 'lock': active_lock }
      return active_lock

  def update_task(self, run_id, task_id, stats, nps, spsa, username):
    lock = self.active_run_lock(str(run_id))
    with lock:
      return self.sync_update_task(run_id, task_id, stats, nps, spsa, username)

  def sync_update_task(self, run_id, task_id, stats, nps, spsa, username):

    run = self.get_run(run_id)
    if task_id >= len(run['tasks']):
      return {'task_alive': False}

    task = run['tasks'][task_id]
    if not task['active'] or not task['pending']:
      return {'task_alive': False}
    if task['worker_info']['username'] != username:
      print('Update_task: Non matching username: ' + username)
      return {'task_alive': False}

    # Guard against incorrect results
    count_games = lambda d: d['wins'] + d['losses'] + d['draws']
    num_games = count_games(stats)
    old_num_games = count_games(task['stats']) if 'stats' in task else num_games
    spsa_games = count_games(spsa) if 'spsa' in run['args'] else 0
    if num_games < old_num_games \
            or (spsa_games > 0 and num_games <= 0) \
            or (spsa_games > 0 and 'stats' in task and num_games <= old_num_games):
      return {'task_alive': False}

    flush = False
    task['stats'] = stats
    task['nps'] = nps
    if num_games >= task['num_games']:
      run['cores'] -= task['worker_info']['concurrency']
      task['pending'] = False # Make pending False before making active false to prevent race in request_task
      task['active'] = False
      flush = True

    update_time = datetime.utcnow()
    task['last_updated'] = update_time
    run['last_updated'] = update_time
    run['results_stale'] = True

    # Update spsa results
    if 'spsa' in run['args'] and spsa_games == spsa['num_games']:
      self.update_spsa(task['worker_info']['unique_key'], run, spsa)

    # Check if SPRT stopping is enabled
    if 'sprt' in run['args']:
      sprt = run['args']['sprt']
      sprt_stats = fishtest.stat_util.SPRT(self.get_results(run, False),
                                  elo0=sprt['elo0'],
                                  alpha=sprt['alpha'],
                                  elo1=sprt['elo1'],
                                  beta=sprt['beta'],
                                  drawelo=sprt['drawelo'])
      if sprt_stats['finished']:
        run['args']['sprt']['state'] = sprt_stats['state']
        self.stop_run(run_id, run)
        flush = True

    self.buffer(run, flush)

    return {'task_alive': task['active']}

  def upload_pgn(self, run_id, pgn_zip):

    self.pgndb.insert({'run_id': run_id, 'pgn_zip': Binary(pgn_zip)})

    return {}

  def failed_task(self, run_id, task_id):
    run = self.get_run(run_id)
    if task_id >= len(run['tasks']):
      return {'task_alive': False}

    task = run['tasks'][task_id]
    if not task['active'] or not task['pending']:
      return {'task_alive': False}

    # Mark the task as inactive: it will be rescheduled
    task['active'] = False
    self.buffer(run, True)

    return {}

  def stop_run(self, run_id, run=None):
    self.clear_params(run_id)
    save_it = False
    if run is None:
      run = self.get_run(run_id)
      save_it = True
    run.pop('cores', None)
    prune_idx = len(run['tasks'])
    for idx, task in enumerate(run['tasks']):
      is_active = task['active']
      task['pending'] = False # Make pending False before making active false to prevent race in request_task
      task['active'] = False
      if 'stats' not in task and not is_active:
        prune_idx = min(idx, prune_idx)
      else:
        prune_idx = idx + 1
    # Truncate the empty tasks
    if prune_idx < len(run['tasks']):
      del run['tasks'][prune_idx:]
    if save_it:
      self.buffer(run, True)
      self.task_time = 0

    return {}

  def approve_run(self, run_id, approver):
    run = self.get_run(run_id)
    # Can't self approve
    if run['args']['username'] == approver:
      return False

    run['approved'] = True
    run['approver'] = approver
    self.buffer(run, True)
    self.task_time = 0
    return True

  def spsa_param_clip_round(self, param, increment, clipping, rounding):
    if clipping == 'old':
      value = param['theta'] + increment
      if value < param['min']:
        value = param['min']
      elif value > param['max']:
        value = param['max']
    else: #clipping == 'careful':
      inc = min(abs(increment), abs(param['theta'] - param['min']) / 2, abs(param['theta'] - param['max']) / 2)
      if inc > 0:
          value = param['theta'] + inc * increment / abs(increment)
      else: #revert to old behavior to bounce off boundary
          value = param['theta'] + increment
          if value < param['min']:
            value = param['min']
          elif value > param['max']:
            value = param['max']

    #'deterministic' rounding calls round() inside the worker.
    #'randomized' says 4.p should be 5 with probability p, 4 with probability 1-p,
    #  and is continuous (albeit after expectation) unlike round().
    if rounding == 'randomized':
        value = math.floor(value + random.uniform(0,1))

    return value

  # Store SPSA parameters for each worker
  spsa_params = {}

  def store_params(self, run_id, worker, params):
    run_id = str(run_id)
    if not run_id in self.spsa_params:
      self.spsa_params[run_id] = {}
    self.spsa_params[run_id][worker] = params

  def get_params(self, run_id, worker):
    run_id = str(run_id)
    if not run_id in self.spsa_params:
      # Should only happen after server restart
      return self.generate_spsa(self.get_run(run_id))['w_params']
    return self.spsa_params[run_id][worker]

  def clear_params(self, run_id):
    run_id = str(run_id)
    if run_id in self.spsa_params:
      del self.spsa_params[run_id]

  def request_spsa(self, run_id, task_id):
    run = self.get_run(run_id)

    if task_id >= len(run['tasks']):
      return {'task_alive': False}
    task = run['tasks'][task_id]
    if not task['active'] or not task['pending']:
      return {'task_alive': False}

    result = self.generate_spsa(run)
    self.store_params(run['_id'], task['worker_info']['unique_key'], result['w_params'])
    return result

  def generate_spsa(self, run):
    result = {
      'task_alive': True,
      'w_params': [],
      'b_params': [],
    }

    spsa = run['args']['spsa']
    if 'clipping' not in spsa:
        spsa['clipping'] = 'old'
    if 'rounding' not in spsa:
        spsa['rounding'] = 'deterministic'

    # Generate the next set of tuning parameters
    iter_local = spsa['iter'] + 1 #assume at least one completed, and avoid division by zero
    for param in spsa['params']:
      c = param['c'] / iter_local ** spsa['gamma']
      flip = 1 if random.getrandbits(1) else -1
      result['w_params'].append({
        'name': param['name'],
        'value': self.spsa_param_clip_round(param, c * flip, spsa['clipping'], spsa['rounding']),
        'R': param['a'] / (spsa['A'] + iter_local) ** spsa['alpha'] / c ** 2,
        'c': c,
        'flip': flip,
      })
      result['b_params'].append({
        'name': param['name'],
        'value': self.spsa_param_clip_round(param, -c * flip, spsa['clipping'], spsa['rounding']),
      })

    return result

  def update_spsa(self, worker, run, spsa_results):
    spsa = run['args']['spsa']
    if 'clipping' not in spsa:
        spsa['clipping'] = 'old'

    spsa['iter'] += int(spsa_results['num_games'] / 2)

    # Store the history every 'freq' iterations.
    # More tuned parameters result in a lower update frequency,
    # so that the required storage (performance) remains constant.
    if 'param_history' not in spsa:
      spsa['param_history'] = []
    L = len(spsa['params'])
    freq = L * 25
    if freq < 100:
      freq = 100
    maxlen = 250000 / freq
    grow_summary = len(spsa['param_history']) < min(maxlen, spsa['iter'] / freq)

    # Update the current theta based on the results from the worker
    # Worker wins/losses are always in terms of w_params
    result = spsa_results['wins'] - spsa_results['losses']
    summary = []
    w_params = self.get_params(run['_id'], worker)
    for idx, param in enumerate(spsa['params']):
      R = w_params[idx]['R']
      c = w_params[idx]['c']
      flip = w_params[idx]['flip']
      param['theta'] = self.spsa_param_clip_round(param, R * c * result * flip, spsa['clipping'], 'deterministic')
      if grow_summary:
        summary.append({
          'theta': param['theta'],
          'R': R,
          'c': c,
        })

    if grow_summary:
      spsa['param_history'].append(summary)
