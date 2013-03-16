import datetime
import math
import os
import sys
import json
from pyramid.security import remember, forget, authenticated_userid
from pyramid.view import view_config, forbidden_view_config
from pyramid.httpexceptions import HTTPFound
from urllib2 import urlopen, HTTPError

from .security import USERS

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
  commit = json.loads(urlopen(FISHCOOKING_URL + '/commits/' + branch).read())
  return commit['sha']

@view_config(route_name='tests_run', renderer='tests_run.mak', permission='modify_db')
def tests_run(request):
  if 'base-branch' in request.POST:
    run_id = request.rundb.new_run(base_tag=request.POST['base-branch'],
                                   new_tag=request.POST['test-branch'],
                                   num_games=int(request.POST['num-games']),
                                   tc=request.POST['tc'],
                                   threads=request.POST['threads'],
                                   book=request.POST['book'],
                                   book_depth=request.POST['book-depth'],
                                   resolved_base=get_sha(request.POST['base-branch']),
                                   resolved_new=get_sha(request.POST['test-branch']),
                                   base_signature=request.POST['base-signature'],
                                   new_signature=request.POST['test-signature'],
                                   info=request.POST['run-info'],
                                   username=authenticated_userid(request))

    request.session.flash('Started test run!')
    return HTTPFound(location=request.route_url('tests'))
  return {}

@view_config(route_name='tests_run_more', permission='modify_db')
def tests_run_more(request):
  if 'num-games' in request.POST:
    run = request.rundb.get_run(request.POST['run'])

    existing_games = 0
    for chunk in run['tasks']:
      existing_games += chunk['num_games']

    num_games = int(request.POST['num-games'])
    if num_games < existing_games:
      return

    # Create new chunks for the games
    new_chunks = request.rundb.generate_tasks(num_games - existing_games)

    run['tasks'] += new_chunks
    run['args']['num_games'] = num_games
    request.rundb.runs.save(run)

    request.session.flash('New games started!')
    return HTTPFound(location=request.route_url('tests'))
  return {}

@view_config(route_name='tests_stop', permission='modify_db')
def tests_stop(request):
  run = request.rundb.get_run(request.POST['run-id'])
  for w in run['tasks']:
    w['pending'] = False
  request.rundb.runs.save(run)

  request.session.flash('Stopped run')
  return HTTPFound(location=request.route_url('tests'))

@view_config(route_name='tests_delete', permission='modify_db')
def tests_delete(request):
  run = request.rundb.get_run(request.POST['run-id'])
  run['deleted'] = True
  for w in run['tasks']:
    w['pending'] = False
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
    # denom99 = 2.58 * math.sqrt((win_ratio * loss_ratio) / (total - 1))
    denom95 = 1.96 * math.sqrt((win_ratio * loss_ratio) / (total - 1))
    elo_win = elo(win_ratio)
    error95 = elo(win_ratio + denom95) - elo_win
    eloInfo = 'ELO: %.2f +-%.1f (95%%)' % (elo_win, error95)
    losInfo = 'LOS: %.1f%%' % (erf(0.707 * (wins-losses)/math.sqrt(wins+losses)) * 50 + 50)
    result['info'].append(eloInfo + ' ' + losInfo)
    result['info'].append('Total: %d W: %d L: %d D: %d' % (int(total), int(wins), int(losses), int(draws)))

    if elo_win + error95 < 0:
      result['style'] = '#FF6A6A'
    elif elo_win - error95 > 0:
      result['style'] = '#44EB44'

  return result

@view_config(route_name='tests_view', renderer='tests_view.mak')
def tests_view(request):
  run = request.rundb.get_run(request.matchdict['id'])
  run['results_info'] = format_results(request.rundb.get_results(run))
  return { 'run': run }

@view_config(route_name='tests', renderer='tests.mak')
def tests(request):
  pending_tasks = []
  failed_tasks = []
  active_tasks = []

  runs = request.rundb.get_runs()
  # Filter out deleted runs
  runs = [r for r in runs if not 'deleted' in r or not r['deleted']]

  for run in runs:
    run['results_info'] = format_results(request.rundb.get_results(run))

    pending = False
    failed = False
    active = False

    for task in run['tasks']:
      if task['active']:
        active = True
        pending = False
      elif task['pending'] and not active:
        pending = True
      elif 'failure' in task:
        failed = True

    if pending:
      pending_tasks.append(run)
    if failed:
      failed_tasks.append(run)
    if active:
      active_tasks.append(run)

  # Filter out pending and active results from finished
  finished = [r for r in runs if r not in pending_tasks and r not in active_tasks]

  machines = request.rundb.get_machines()
  current_time = datetime.datetime.utcnow()
  for machine in machines:
    delta = current_time - machine['last_updated']
    if delta.days != 0:
      machine['last_updated'] = 'Over a day ago!'
    else:
      machine['last_updated'] = '%d seconds ago' % (delta.seconds)

  # Calculate time remaining for pending and active tests
  def parse_tc(tc):
    chunks = tc.split('+')
    return (float(chunks[0]) + 40*float(chunks[1])) * 2

  # Calculate remaining number of games for pending and active tests
  def remaining_games(run):
    res = run['results']
    return run['args']['num_games'] - res['wins'] - res['losses'] - res['draws']

  cores = sum([int(m['concurrency']) for m in machines])
  if cores > 0:
    pending_hours = sum([parse_tc(r['args']['tc']) * remaining_games(r) for r in pending_tasks + active_tasks]) / (60*60)
    pending_hours /= cores
  else:
    pending_hours = '- -'

  return {
    'machines': machines,
    'pending': pending_tasks,
    'pending_hours': '%.1f' % (pending_hours),
    'failed': failed_tasks,
    'active': active_tasks,
    'runs': finished
  }
