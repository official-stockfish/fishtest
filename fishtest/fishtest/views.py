import ast
import datetime
import math
import transaction
import os
import persistent, persistent.dict, persistent.list
import sys
import ujson
from pyramid.view import view_config
from pyramid.httpexceptions import HTTPFound
from urllib2 import urlopen, HTTPError
from ZODB.FileStorage import FileStorage
from ZODB.DB import DB

# For tasks
sys.path.append(os.path.expanduser('~/fishtest'))
from tasks.games import run_games
from tasks.celery import celery

FLOWER_URL = 'http://localhost:5555'

def get_db():
  storage = FileStorage(os.path.expanduser('~/testruns.db'))
  db = DB(storage)
  connection = db.open()
  return connection.root()

def get_tasks_db():
  db = get_db()
  if 'tasks' not in db:
    db['tasks'] = persistent.dict.PersistentDict()
  return db['tasks']

@view_config(route_name='home', renderer='mainpage.mak')
def mainpage(request):
  return {'project': 'fishtest'}

@view_config(route_name='tests_run', renderer='tests_run.mak')
def tests_run(request):
  if 'base-branch' in request.POST:
    args = {
      'base_branch': request.POST['base-branch'],
      'new_branch': request.POST['test-branch'],
      'num_games': request.POST['num-games'],
      'tc': request.POST['tc'],
    }
    new_task = run_games.delay(**args)

    tasks_db = get_tasks_db()
    tasks_db[new_task.id] = {'args': args,
                             'start_time': datetime.datetime.now() }
    transaction.get().commit()

    request.session.flash('Started test run!')
    return HTTPFound(location=request.route_url('tests'))
  return {}

def elo(win_ratio):
  return 400 * math.log10(win_ratio / (1 - win_ratio))

def format_results(results):
  wins = float(results['wins'])
  losses = float(results['losses'])
  draws = float(results['draws'])
  total = wins + draws + losses
  if total < 2:
    return 'Not enough games'
  win_ratio = (wins + (draws / 2)) / total
  loss_ratio = 1 - win_ratio
  draw_ratio = draws / total
  denom99 = 2.58 * math.sqrt((win_ratio * loss_ratio) / (total - 1))
  denom95 = 1.96 * math.sqrt((win_ratio * loss_ratio) / (total - 1))
  elo_win = elo(win_ratio)
  result = 'ELO: %.2f +- 99%%: %.2f 95%%: %.2f\n' % (elo_win, elo(win_ratio + denom99) - elo_win, elo(win_ratio + denom95) - elo_win)
  result += 'Wins: %d Losses: %d Draws: %d Total: %d' % (int(wins), int(losses), int(draws), int(total))
  return result

def format_name(args):
  return '%s vs %s - %s @ %s' % (args['new_branch'], args['base_branch'], args['num_games'], args['tc'])

def get_celery_stats(tasks_db):
  machines = {}
  waiting = []

  try:
    workers = ujson.loads(urlopen(FLOWER_URL + '/api/workers').read())
    tasks = ujson.loads(urlopen(FLOWER_URL + '/api/tasks').read())

    # Update task states
    for id, task in tasks.iteritems():
      if id in tasks_db:
        tasks_db[id]['raw'] = task

    for worker, info in workers.iteritems():
      if not info['status']:
        continue
      machine_tasks = []
      for task in info['running_tasks']:
        if task['id'] in tasks and tasks[task['id']]['state'] == 'REVOKED':
          continue

        job_result = celery.AsyncResult(task['id'])
        # Workaround celery throwing exception accessing task status.
        status = None
        for _ in xrange(5):
          try:
            status = {'status': job_result.status}
          except:
            pass

        if status == None:
          continue
        results = 'Pending...'
        if job_result.result != None:
          status['result'] = job_result.result
          results = format_results(status['result'])

        tasks_db[task['id']]['status'] = status

        machine_tasks.append({
          'name': format_name(tasks_db[task['id']]['args']),
          'results': results,
        })

      machines[worker] = machine_tasks
  except HTTPError as e:
    pass

  transaction.get().commit()
  return (machines, tasks)

@view_config(route_name='tests', renderer='tests.mak')
def tests(request):
  tasks_db = get_tasks_db()

  machines, tasks = get_celery_stats(tasks_db)
  waiting = []
  failed = []
  for task, info in tasks.iteritems():
    if info['state'] == 'PENDING':
      waiting.append(format_name(tasks_db[task]['args']))
    elif info['state'] == 'FAILURE' and info['kwargs'] != None:
      failed.append('---')

  runs = [t for t in tasks_db.values()]
  runs = sorted(runs, key=lambda k: k['start_time'], reverse=True)

  for run in runs:
    run['results'] = 'Pending...'
    if 'status' in run and 'result' in run['status']:
      run['results'] = format_results(run['status']['result'])
    elif 'raw' in run and 'result' in run['raw']:
      try:
        run['results'] = format_results(ast.literal_eval(run['raw']['result']))
      except:
        pass 

    run['name'] = format_name(run['args'])

  return {
    'machines': machines,
    'waiting': waiting,
    'failed': failed,
    'runs': runs 
  }
