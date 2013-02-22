import ast
import datetime
import math
import os
import sh
import sys
import ujson
from pyramid.security import remember, forget, authenticated_userid
from pyramid.view import view_config, forbidden_view_config
from pyramid.httpexceptions import HTTPFound
from urllib2 import urlopen, HTTPError

from .security import USERS

# For tasks
dn = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(dn,'../..'))
from tasks.games import run_games
from tasks.celery import celery

# Celery Flower is assumed to be on the same machine, if not user should use
# ssh with port forwarding to access the remote host.
FLOWER_URL = 'http://localhost:5555'
FISHCOOKING_URL = 'https://api.github.com/repos/mcostalba/FishCooking'

@view_config(route_name='home', renderer='mainpage.mak')
def mainpage(request):
  return {}

@view_config(route_name='login', renderer='mainpage.mak')
@forbidden_view_config(renderer='mainpage.mak')
def login(request):
  login_url = request.route_url('login')
  referrer = request.url
  if referrer == login_url:
      referrer = '/' # never use the login form itself as came_from
  came_from = request.params.get('came_from', referrer)

  if 'form.submitted' in request.params:
    username = request.params['username']
    password = request.params['password']
    if USERS.get(username) == password:
      headers = remember(request, username)
      return HTTPFound(location=came_from, headers=headers)
  #TODO: failed login handling
  return {}

def get_sha(branch):
  """Resolves the git branch to sha commit"""
  commit = ujson.loads(urlopen(FISHCOOKING_URL + '/commits/' + branch).read())
  return commit['sha']

@view_config(route_name='tests_run', renderer='tests_run.mak', permission='modify_db')
def tests_run(request):
  if 'base-branch' in request.POST:
    run_id = request.rundb.new_run(base_tag=request.POST['base-branch'],
                                   new_tag=request.POST['test-branch'],
                                   num_games=int(request.POST['num-games']),
                                   tc=request.POST['tc'],
                                   resolved_base=get_sha(request.POST['base-branch']),
                                   resolved_new=get_sha(request.POST['test-branch']),
                                   base_signature=request.POST['base-signature'],
                                   new_signature=request.POST['test-signature'],
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

@view_config(route_name='tests_delete', permission='modify_db')
def tests_delete(request):
  run = request.rundb.get_run(request.POST['run-id'])
  run['deleted'] = True
  for w in run['worker_results']:
    if 'celery_id' in w:
      celery.control.revoke(w['celery_id'])
  run['worker_results'] = []
  request.rundb.runs.save(run)

  request.session.flash('Deleted run')
  return HTTPFound(location=request.route_url('tests'))

def elo(win_ratio):
  return 400 * math.log10(win_ratio / (1 - win_ratio))

def erf(x):
  # save the sign of x
  sign = 1 if x >= 0 else -1
  x = abs(x)

  # constants
  a1 =  0.254829592
  a2 = -0.284496736
  a3 =  1.421413741
  a4 = -1.453152027
  a5 =  1.061405429
  p  =  0.3275911

  # A&S formula 7.1.26
  t = 1.0/(1.0 + p*x)
  y = 1.0 - (((((a5*t + a4)*t) + a3)*t + a2)*t + a1)*t*math.exp(-x*x)
  return sign*y # erf(-x) = -erf(x)

def format_results(results):
  result = {'style': '', 'info': []}
  wins = float(results['wins'])
  losses = float(results['losses'])
  draws = float(results['draws'])
  total = wins + draws + losses
  if total < 10:
    result['info'].append('Pending...')
    return result
  win_ratio = (wins + (draws / 2)) / total
  loss_ratio = 1 - win_ratio
  draw_ratio = draws / total
  if abs(win_ratio) < 1e-6 or abs(win_ratio - 1.0) < 1e-6:
    result['info'].append('ELO: unknown')
  else:
    denom99 = 2.58 * math.sqrt((win_ratio * loss_ratio) / (total - 1))
    denom95 = 1.96 * math.sqrt((win_ratio * loss_ratio) / (total - 1))
    elo_win = elo(win_ratio)
    error99 = elo(win_ratio + denom99) - elo_win
    error95 = elo(win_ratio + denom95) - elo_win
    eloInfo = 'ELO: %.2f +-%.2f (95%%) +-%.2f (99%%)' % (elo_win, error95, error99)
    losInfo = 'LOS: %.2f%%' % (erf(0.707 * (wins-losses)/math.sqrt(wins+losses)) * 50 + 50)
    result['info'].append(eloInfo + ' ' + losInfo)
    result['info'].append('Total: %d W: %d L: %d D: %d' % (int(total), int(wins), int(losses), int(draws)))

    if elo_win + error95 < 0:
      result['style'] = '#FF6A6A'
    elif elo_win - error95 > 0:
      result['style'] = '#44EB44'

  return result

def get_celery_stats():
  machines = {}
  tasks = []

  try:
    workers = ujson.loads(urlopen(FLOWER_URL + '/api/workers').read())
    tasks = ujson.loads(urlopen(FLOWER_URL + '/api/tasks').read())

    for worker, info in workers.iteritems():
      if not info['status']:
        continue
      machines[worker] = 'Idle' if len(info['running_tasks']) == 0 else 'Running tasks'
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
  # Filter out deleted runs
  runs = [r for r in runs if not 'deleted' in r or not r['deleted']]

  for run in runs:
    run['results'] = format_results(request.rundb.get_results(run))

    waiting = False
    failed = False
    active = False

    for worker in run['worker_results']:
      if worker['celery_id'] in tasks:
        task = tasks[worker['celery_id']]
        if not active and task['state'] == 'PENDING':
          waiting = True
        elif task['state'] == 'FAILURE' and not 'terminated' in task:
          failed = True
        elif task['state'] == 'STARTED':
          active = True
          waiting = False

    if waiting:
      waiting_tasks.append(run)
    if failed:
      failed_tasks.append(run)
    if active:
      active_tasks.append(run)

  # Filter out pending and active results from finished
  runs = [r for r in runs if r not in waiting_tasks and r not in active_tasks]

  return {
    'machines': machines,
    'waiting': waiting_tasks,
    'failed': failed_tasks,
    'active': active_tasks,
    'runs': runs
  }
