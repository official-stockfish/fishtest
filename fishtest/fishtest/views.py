import datetime
import math
import os
import sys
import json
from pyramid.security import remember, forget, authenticated_userid
from pyramid.view import view_config, forbidden_view_config
from pyramid.httpexceptions import HTTPFound
from urllib2 import urlopen, HTTPError

FISHCOOKING_URL = 'https://api.github.com/repos/mcostalba/FishCooking'

@view_config(route_name='home', renderer='mainpage.mak')
def mainpage(request):
  return HTTPFound(location=request.route_url('tests'))

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
    token = request.userdb.authenticate(username, password)
    if 'error' not in token:
      headers = remember(request, username)
      return HTTPFound(location=came_from, headers=headers)

    request.session.flash('Incorrect password')

  return {}

@view_config(route_name='signup', renderer='signup.mak', permission='modify_db')
def signup(request):
  if 'form.submitted' in request.params:
    result = request.userdb.create_user(
      username=request.params['username'],
      password=request.params['password'],
      email=request.params['email']
    )

    if not result:
      request.session.flash('Invalid username')
    else:
      return HTTPFound(location=request.route_url('login'))

  return {}

@view_config(route_name='users', renderer='users.mak')
def users(request):
  return {'users': request.userdb.get_users()}

def get_sha(branch):
  """Resolves the git branch to sha commit"""
  commit = json.loads(urlopen(FISHCOOKING_URL + '/commits/' + branch).read())
  return commit['sha']

def validate_form(request):
  data = {
    'base_tag' : request.POST['base-branch'],
    'new_tag' : request.POST['test-branch'],
    'tc' : request.POST['tc'],
    'book' : request.POST['book'],
    'book_depth' : request.POST['book-depth'],
    'resolved_base' : request.POST['base-branch'],
    'resolved_new' : request.POST['test-branch'],
    'base_signature' : request.POST['base-signature'],
    'new_signature' : request.POST['test-signature'],
    'username' : authenticated_userid(request),
  }

  if len([v for v in data.values() if len(v) == 0]) > 0:
    return data, False

  data['resolved_base'] = get_sha(data['resolved_base'])
  data['resolved_new'] = get_sha(data['resolved_new'])

  # Integer parameters
  data['num_games'] = int(request.POST['num-games'])
  data['threads'] = int(request.POST['threads'])
  data['priority'] = int(request.POST['priority'])

  # Optional
  data['info'] = request.POST['run-info']

  return data, True

@view_config(route_name='tests_run', renderer='tests_run.mak', permission='modify_db')
def tests_run(request):
  if 'base-branch' in request.POST:
    data, valid = validate_form(request)
    if valid:
      run_id = request.rundb.new_run(**data)
      request.session.flash('Started test run!')
      return HTTPFound(location=request.route_url('tests'))
    else:
      request.session.flash('Please fill all required fields')
  return {}

@view_config(route_name='tests_modify', permission='modify_db')
def tests_modify(request):
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
    run['args']['priority'] = int(request.POST['priority'])
    request.rundb.runs.save(run)

    request.session.flash('Run successfully modified!')
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
  finished = []

  runs = request.rundb.get_runs()

  for run in runs:

    if 'deleted' in run and run['deleted']:
      continue

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
    elif failed:
      failed_tasks.append(run)
    elif active:
      active_tasks.append(run)
    else:
      finished.append(run)

  machines = request.rundb.get_machines()
  current_time = datetime.datetime.utcnow()
  for machine in machines:
    delta = current_time - machine['last_updated']
    if delta.days != 0:
      machine['last_updated'] = 'Over a day ago!'
    else:
      machine['last_updated'] = '%d seconds ago' % (delta.seconds)

  def remaining_hours(run):
    r = run['results']
    remaining_games = run['args']['num_games'] - r['wins'] - r['losses'] - r['draws']
    chunks = run['args']['tc'].split('+')
    game_secs = (float(chunks[0]) + 40 * float(chunks[1])) * 2
    return game_secs * remaining_games * int(run['args'].get('threads', 1)) / (60*60)

  cores = sum([int(m['concurrency']) for m in machines])
  if cores > 0:
    pending_hours = 0
    for run in pending_tasks + active_tasks:
      eta = remaining_hours(run) / cores
      pending_hours += eta
      info = run['results_info']
      if 'Pending...' in info['info']:
        info['info'] = ['Pending... (%.1f hrs)' % (eta)]

  else:
    pending_hours = '- -'

  def total_games(run):
    res = run['results']
    return res['wins'] + res['draws'] + res['losses']
  games_played = sum([total_games(r) for r in finished])

  return {
    'machines': machines,
    'pending': pending_tasks,
    'pending_hours': '%.1f' % (pending_hours),
    'failed': failed_tasks,
    'active': active_tasks,
    'finished': finished,
    'games_played': games_played,
    'cores': cores,
  }
