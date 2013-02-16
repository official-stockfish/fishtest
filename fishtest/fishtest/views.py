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
  # Default to origin branch
  if '/' not in branch:
    branch = 'origin/' + branch
  sh.git.fetch(branch.split('/')[0])
  return sh.git.log(branch, n=1, no_color=True, pretty='format:%H a').split()[1]

@view_config(route_name='tests_run', renderer='tests_run.mak')
def tests_run(request):
  if 'base-branch' in request.POST:
    run_id = request.rundb.new_run(base_tag=request.POST['base-branch'],
                                   new_tag=request.POST['test-branch'],
                                   num_games=int(request.POST['num-games']),
                                   tc=request.POST['tc'],
                                   resolved_base=get_sha(request.POST['base-branch']),
                                   resolved_new=get_sha(request.POST['test-branch']),
                                   name=request.POST['run-name'],
                                   info=request.POST['run-info'])

    # Start a celery task for each chunk
    new_run = request.rundb.get_run(run_id)
    for idx, chunk in enumerate(new_run['worker_results']):
      new_task = run_games.delay(new_run['_id'], idx)
      chunk['celery_id'] = new_task.id

    request.rundb.runs.save(new_run)

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
  if abs(win_ratio) < 1e-6 or abs(win_ratio - 1.0) < 1e-6:
    result = 'ELO: unknown'
  else:
    elo_win = elo(win_ratio)
    result = 'ELO: %.2f +- 99%%: %.2f 95%%: %.2f\n' % (elo_win, elo(win_ratio + denom99) - elo_win, elo(win_ratio + denom95) - elo_win)
  result += 'Wins: %d Losses: %d Draws: %d Total: %d' % (int(wins), int(losses), int(draws), int(total))
  return result

def format_name(args):
  repo = 'https://github.com/mcostalba/FishCooking'
  def format_sha(sha):
    return '<a href="%s/commit/%s">%s</a>' % (repo, sha, sha[:7])

  new_sha = format_sha(args['resolved_new'])
  base_sha = format_sha(args['resolved_base'])

  diff = '<a href="%s/compare/%s...%s">Diff</a>' % (repo, args['resolved_base'][:7], args['resolved_new'][:7])
  name = '%s(%s) vs %s(%s) - %d @ %s - %s' % (args['new_tag'], new_sha, args['base_tag'], base_sha, args['num_games'], args['tc'], diff)
  if 'name' in args:
    name = args['name'] + ': ' + name
  return name

def get_celery_stats():
  machines = {}
  tasks = []

  try:
    workers = ujson.loads(urlopen(FLOWER_URL + '/api/workers').read())
    tasks = ujson.loads(urlopen(FLOWER_URL + '/api/tasks').read())

    for worker, info in workers.iteritems():
      if not info['status']:
        continue
      machines[worker] = len(info['running_tasks'])
  except HTTPError as e:
    pass

  return (machines, tasks)

@view_config(route_name='tests', renderer='tests.mak')
def tests(request):
  machines, tasks = get_celery_stats()
  waiting_tasks = []
  failed_tasks = []
  active_tasks = []

  runs = request.rundb.get_runs()
  for run in runs:
    run['results'] = format_results(request.rundb.get_results(run))
    if 'info' in run['args']:
      run['results'] += '\nInfo: ' + run['args']['info']

    run['name'] = format_name(run['args'])

    waiting = False
    failed = False
    active = False

    for worker in run['worker_results']:
      if worker['celery_id'] in tasks:
        task = tasks[worker['celery_id']]
        if task['state'] == 'PENDING':
          waiting = True
        elif task['state'] == 'FAILURE':
          failed = True
        elif task['state'] == 'STARTED':
          active = True

    if waiting:
      waiting_tasks.append(run['name'])
    if failed:
      failed_tasks.append(run['name'])
    if active:
      active_tasks.append(run)

  # Filter pending results
  runs = [r for r in runs if r['results'] != 'Pending...']

  return {
    'machines': machines,
    'waiting': waiting_tasks,
    'failed': failed_tasks,
    'active': active_tasks,
    'runs': runs 
  }
