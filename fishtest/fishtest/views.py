import datetime
import os
import sys
import json
import requests
from collections import defaultdict
from pyramid.security import remember, forget, authenticated_userid
from pyramid.view import view_config, forbidden_view_config
from pyramid.httpexceptions import HTTPFound

import stat_util

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

def delta_date(date):
  if date != datetime.datetime.min:
    diff = datetime.datetime.utcnow() - date
    if diff.days != 0:
      delta = '%d days ago' % (diff.days)
    elif diff.seconds / 3600 > 1:
      delta = '%d hours ago' % (diff.seconds / 3600)
    elif diff.seconds / 60 > 1:
      delta = '%d minutes ago' % (diff.seconds / 60)
    else:
      delta = '%d seconds ago' % (diff.seconds)
  else:
    delta = 'Never'
  return delta

@view_config(route_name='users', renderer='users.mak')
def users(request):
  info = {}
  for username in request.userdb.get_users():
    info[username] = {'username': username, 'completed': 0, 'last_updated': datetime.datetime.min}

  for run in request.rundb.get_runs():
    for task in run['tasks']:
      if 'worker_info' not in task:
        continue
      username = task['worker_info'].get('username', None)
      if username == None:
        continue
      info[username]['last_updated'] = max(task['last_updated'], info[username]['last_updated'])
      info[username]['completed'] += task['num_games']

  users = []
  for username in request.userdb.get_users():
    user = info[username]
    user['last_updated'] = delta_date(user['last_updated'])
    users.append(user)

  users.sort(key=lambda k: k['completed'], reverse=True)
  return {'users': users}

def get_sha(branch):
  """Resolves the git branch to sha commit"""
  commit = requests.get(FISHCOOKING_URL + '/commits/' + branch).json()
  return commit['sha']

def validate_form(request):
  data = {
    'base_tag' : request.POST['base-branch'],
    'new_tag' : request.POST['test-branch'],
    'tc' : request.POST['tc'],
    'book' : request.POST['book'],
    'book_depth' : request.POST['book-depth'],
    'base_signature' : request.POST['base-signature'],
    'new_signature' : request.POST['test-signature'],
    'base_options' : request.POST['base-options'],
    'new_options' : request.POST['new-options'],
    'username' : authenticated_userid(request),
  }

  if len([v for v in data.values() if len(v) == 0]) > 0:
    return data, False

  if 'resolved_base' in request.POST:
    data['resolved_base'] = request.POST['resolved_base']
    data['resolved_new'] = request.POST['resolved_new']
  else:
    data['resolved_base'] = get_sha(data['base_tag'])
    data['resolved_new'] = get_sha(data['new_tag'])

  stop_rule = request.POST['stop_rule']

  # Integer parameters
  if stop_rule == 'sprt':
    data['sprt'] = {
      'elo0': 0.0,
      'alpha': 0.05,
      'elo1': float(request.POST['sprt_elo1']),
      'beta': 0.05,
      'drawelo': 240.0,
    }
    data['num_games'] = 64000
  else:
    data['num_games'] = int(request.POST['num-games'])
    if data['num_games'] <= 0:
      return data, False

  data['threads'] = int(request.POST['threads'])
  data['priority'] = int(request.POST['priority'])

  if data['threads'] <= 0:
    return data, False

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

  run_args = {}
  if 'id' in request.params:
    run_args = request.rundb.get_run(request.params['id'])['args']

  return {
    'args': run_args,
  }

@view_config(route_name='tests_modify', permission='modify_db')
def tests_modify(request):
  if 'num-games' in request.POST:
    run = request.rundb.get_run(request.POST['run'])

    existing_games = 0
    for chunk in run['tasks']:
      existing_games += chunk['num_games']

    num_games = int(request.POST['num-games'])
    if num_games < existing_games:
      request.session.flash('Reducing number of games not supported yet')
      return HTTPFound(location=request.route_url('tests'))

    # Create new chunks for the games
    new_chunks = request.rundb.generate_tasks(num_games - existing_games)

    run['finished'] = False
    run['tasks'] += new_chunks
    run['args']['num_games'] = num_games
    run['args']['priority'] = int(request.POST['priority'])
    request.rundb.runs.save(run)

    request.session.flash('Run successfully modified!')
    return HTTPFound(location=request.route_url('tests'))
  return {}

@view_config(route_name='tests_stop', permission='modify_db')
def tests_stop(request):
  request.rundb.stop_run(request.POST['run-id'])

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

def format_results(results):
  result = {'style': '', 'info': []}

  # win/loss/draw count
  WLD = [results['wins'], results['losses'], results['draws']]

  # If the score is 0% or 100% the formulas will crash
  # anyway the statistics are only asymptotic
  if WLD[0] == 0 or WLD[1] == 0:
    result['info'].append('Pending...')
    return result

  elo, elo95, los = stat_util.get_elo(WLD)

  # Display the results
  eloInfo = 'ELO: %.2f +-%.1f (95%%)' % (elo, elo95)
  losInfo = 'LOS: %.1f%%' % (los * 100)

  result['info'].append(eloInfo + ' ' + losInfo)
  result['info'].append('Total: %d W: %d L: %d D: %d' % (sum(WLD), WLD[0], WLD[1], WLD[2]))

  if los < 0.05:
    result['style'] = '#FF6A6A'
  elif los > 0.95:
    result['style'] = '#44EB44'

  return result

@view_config(route_name='tests_view', renderer='tests_view.mak')
def tests_view(request):
  run = request.rundb.get_run(request.matchdict['id'])
  run['results_info'] = format_results(request.rundb.get_results(run))

  run_args = []
  for name in ['new_tag', 'new_signature', 'new_options', 'resolved_new',
               'base_tag', 'base_signature', 'base_options', 'resolved_base',
               'num_games', 'tc', 'threads', 'book', 'book_depth',
               'priority', 'username', 'info']:
    run_args.append((name, run['args'].get(name, '-')))
  run_args.append(('id', run['_id']))

  for task in run['tasks']:
    last_updated = task.get('last_updated', datetime.datetime.min)
    task['last_updated'] = delta_date(last_updated)

  return { 'run': run, 'run_args': run_args }

@view_config(route_name='tests', renderer='tests.mak')
def tests(request):
  runs = { 'pending':[], 'failed':[], 'active':[], 'finished':[] }

  all_runs = request.rundb.get_runs()

  for run in all_runs:

    if 'deleted' in run and run['deleted']:
      continue

    run['results_info'] = format_results(request.rundb.get_results(run))

    state = 'finished'

    if not run['finished']:
      for task in run['tasks']:
        if 'failure' in task:
          state = 'failed'
          break
        elif task['active']:
          state = 'active'
        elif task['pending'] and not state == 'active':
          state = 'pending'

      if state == 'finished':
        run['finished'] = True
        request.rundb.runs.save(run)

    runs[state].append(run)

  runs['pending'].sort(key = lambda run: run['args']['priority'])
  machines = request.rundb.get_machines()
  for machine in machines:
    machine['last_updated'] = delta_date(machine['last_updated'])
  machines.reverse()

  def remaining_hours(run):
    r = run['results']
    expected_games = run['args']['num_games']
    if 'sprt' in run['args']:
      expected_games = 16000
    remaining_games = max(0, expected_games - r['wins'] - r['losses'] - r['draws'])
    chunks = run['args']['tc'].split('+')
    game_secs = (float(chunks[0]) + 40 * float(chunks[1])) * 2
    return game_secs * remaining_games * int(run['args'].get('threads', 1)) / (60*60)

  cores = sum([int(m['concurrency']) for m in machines])
  if cores > 0:
    pending_hours = 0
    for run in runs['pending'] + runs['active']:
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
  games_played = sum([total_games(r) for r in runs['finished']])

  return {
    'runs': runs,
    'machines': machines,
    'pending_hours': '%.1f' % (pending_hours),
    'games_played': games_played,
    'cores': cores,
  }
