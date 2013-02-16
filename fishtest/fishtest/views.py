import ast
import datetime
import math
import os
import sh
import sys
import ujson
from pyramid.view import view_config
from pyramid.httpexceptions import HTTPFound
from urllib2 import urlopen, HTTPError

# For tasks
sys.path.append(os.path.expanduser('~/fishtest'))
from tasks.games import run_games
from tasks.celery import celery

FLOWER_URL = 'http://localhost:5555'

@view_config(route_name='home', renderer='mainpage.mak')
def mainpage(request):
  return {'project': 'fishtest'}

def get_sha(branch):
  """Resolves the git branch (ie. master, or glinscott/master) to sha commit"""
  sh.cd(os.path.expanduser('~/stockfish'))
  sh.git.fetch(branch.split('/')[0])
  return sh.git.log(branch, n=1, no_color=True, pretty='format:%H').split()[1]

@view_config(route_name='tests_run', renderer='tests_run.mak')
def tests_run(request):
  if 'base-branch' in request.POST:
    args = {
      'base_branch': request.POST['base-branch'],
      'new_branch': request.POST['test-branch'],
      'num_games': int(request.POST['num-games']),
      'tc': request.POST['tc'],
    }

    run_id = request.rundb.new_run(base_tag=args['base_branch'],
                                   new_tag=args['new_branch'],
                                   num_games=args['num_games'],
                                   tc=args['tc'],
                                   resolved_base=get_sha(args['base_branch']),
                                   resolved_new=get_sha(args['new_branch']))

    new_task = run_games.delay(**args)

    # TODO: Fix this up once we convert to chunked runs
    new_run = request.rundb.runs.find_one(run_id)
    new_run['worker_results'][0]['celery_id'] = new_task.id
    request.rundb.runs.save(new_run)
    # End TODO

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
    return 'Pending...'
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
  return '%s vs %s - %d @ %s' % (args['new_tag'], args['base_tag'], args['num_games'], args['tc'])

def get_celery_stats():
  machines = {}
  waiting = []

  try:
    workers = ujson.loads(urlopen(FLOWER_URL + '/api/workers').read())
    tasks = ujson.loads(urlopen(FLOWER_URL + '/api/tasks').read())

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
          results = format_results(job_result.result)

        machine_tasks.append({
          'name': '--', #format_name(tasks_db[task['id']]['args']),
          'results': results,
        })

      machines[worker] = machine_tasks
  except HTTPError as e:
    pass

  return (machines, tasks)

@view_config(route_name='tests', renderer='tests.mak')
def tests(request):
  machines, tasks = get_celery_stats()
  waiting_tasks = []
  failed_tasks = []

  runs = request.rundb.get_runs()
  for run in runs:
    run['results'] = format_results(request.rundb.get_results(run))
    run['name'] = format_name(run['args'])

    waiting = False
    failed = False
    for worker in run['worker_results']:
      if worker['celery_id'] in tasks:
        task = tasks[worker['celery_id']]
        if task['state'] == 'PENDING':
          waiting = True
        elif task['state'] == 'FAILED':
          failed = True
        # TODO: remove this once we have tasks logging their w/l/d to mongo directly
        elif task['state'] == 'SUCCESS':
          run['results'] = format_results(ast.literal_eval(task['result']))

    if waiting:
      waiting_tasks.append(run['name'])
    if failed:
      failed_tasks.append(run['name'])

  return {
    'machines': machines,
    'waiting': waiting_tasks,
    'failed': failed_tasks,
    'runs': runs 
  }
