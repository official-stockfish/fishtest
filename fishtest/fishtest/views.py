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
  for u in request.userdb.get_users():
    username = u['username']
    info[username] = {'username': username, 'completed': 0, 'tests': 0, 'tests_repo': u.get('tests_repo', ''), 'last_updated': datetime.datetime.min}

  for run in request.rundb.get_runs():
    if 'username' in run['args']:
      username = run['args']['username']
      info[username]['tests'] += 1

    for task in run['tasks']:
      if 'worker_info' not in task:
        continue
      username = task['worker_info'].get('username', None)
      if username == None:
        continue
      info[username]['last_updated'] = max(task['last_updated'], info[username]['last_updated'])
      info[username]['completed'] += task['num_games']

  users = []
  for u in info.keys():
    user = info[u]
    user['last_updated'] = delta_date(user['last_updated'])
    users.append(user)

  users.sort(key=lambda k: k['completed'], reverse=True)
  return {'users': users}

def get_sha(branch, repo_url):
  """Resolves the git branch to sha commit"""
  # Convert from https://github.com/<user>/<repo>
  # To https://api.github.com/repos/<user>/<repo>
  r = repo_url.split('github.com')
  api_url = ''.join([r[0], 'api.github.com/repos',r[1]])
  commit = requests.get(api_url + '/commits/' + branch).json()
  return commit.get('sha', '')

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
    'tests_repo' : request.POST['tests-repo'],
  }

  if len([v for v in data.values() if len(v) == 0]) > 0:
    return data, 'Missing required option'

  data['regression_test'] = request.POST['test_type'] == 'Regression'
  if data['regression_test']:
    data['base_tag'] = data['new_tag']
    data['base_signature'] = data['new_signature']
    data['base_options'] = data['new_options']

  if 'resolved_base' in request.POST:
    data['resolved_base'] = request.POST['resolved_base']
    data['resolved_new'] = request.POST['resolved_new']
  else:
    data['resolved_base'] = get_sha(data['base_tag'], data['tests_repo'])
    data['resolved_new'] = get_sha(data['new_tag'], data['tests_repo'])
    u = request.userdb.get_user(data['username'])
    if u['tests_repo'] != data['tests_repo']:
      u['tests_repo'] = data['tests_repo']
      request.userdb.users.save(u)

  if len(data['resolved_base']) == 0 or len(data['resolved_new']) == 0:
    return data, 'Unable to find branch!'

  stop_rule = request.POST['stop_rule']

  # Integer parameters
  if stop_rule == 'sprt':
    data['sprt'] = {
      'elo0': float(request.POST['sprt_elo0']),
      'alpha': 0.05,
      'elo1': float(request.POST['sprt_elo1']),
      'beta': 0.05,
      'drawelo': 240.0,
    }
    # Arbitrary limit on number of games played.  Shouldn't be hit in practice
    data['num_games'] = 128000
  else:
    data['num_games'] = int(request.POST['num-games'])
    if data['num_games'] <= 0:
      return data, 'Number of games must be >= 0'

  data['threads'] = int(request.POST['threads'])
  data['priority'] = int(request.POST['priority'])

  if data['threads'] <= 0:
    return data, 'Threads must be >= 0'

  # Optional
  data['info'] = request.POST['run-info']

  return data, ''

@view_config(route_name='tests_run', renderer='tests_run.mak', permission='modify_db')
def tests_run(request):
  if 'base-branch' in request.POST:
    data, error_message = validate_form(request)
    if len(error_message) == 0:
      run_id = request.rundb.new_run(**data)
      request.session.flash('Started test run!')
      return HTTPFound(location=request.route_url('tests'))
    else:
      request.session.flash(error_message)

  run_args = {}
  if 'id' in request.params:
    run_args = request.rundb.get_run(request.params['id'])['args']

  username = authenticated_userid(request)
  u = request.userdb.get_user(username)

  return { 'args': run_args, 'tests_repo': u['tests_repo'] }

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

def format_results(rundb, run):
  result = {'style': '', 'info': []}

  # win/loss/draw count
  run_results = rundb.get_results(run)
  WLD = [run_results['wins'], run_results['losses'], run_results['draws']]

  # If the score is 0% or 100% the formulas will crash
  # anyway the statistics are only asymptotic
  if WLD[0] == 0 or WLD[1] == 0:
    result['info'].append('Pending...')
    return result

  state = 'unknown'
  if 'sprt' in run['args']:
    sprt = run['args']['sprt']
    state = sprt.get('state', '')

    stats = stat_util.SPRT(run_results,
                           elo0=sprt['elo0'],
                           alpha=sprt['alpha'],
                           elo1=sprt['elo1'],
                           beta=sprt['beta'],
                           drawelo=sprt['drawelo'])
    result['info'].append('LLR: %.2f (%.2lf,%.2lf)' % (stats['llr'], stats['lower_bound'], stats['upper_bound']))
  else:
    elo, elo95, los = stat_util.get_elo(WLD)

    # Display the results
    eloInfo = 'ELO: %.2f +-%.1f (95%%)' % (elo, elo95)
    losInfo = 'LOS: %.1f%%' % (los * 100)

    result['info'].append(eloInfo + ' ' + losInfo)

    if los < 0.05:
      state = 'rejected'
    elif los > 0.95:
      state = 'accepted'

  result['info'].append('Total: %d W: %d L: %d D: %d' % (sum(WLD), WLD[0], WLD[1], WLD[2]))

  if state == 'rejected':
    result['style'] = '#FF6A6A'
  elif state == 'accepted':
    result['style'] = '#44EB44'
  return result

@view_config(route_name='tests_view', renderer='tests_view.mak')
def tests_view(request):
  run = request.rundb.get_run(request.matchdict['id'])
  run['results_info'] = format_results(request.rundb, run)

  run_args = []
  for name in ['new_tag', 'new_signature', 'new_options', 'resolved_new',
               'base_tag', 'base_signature', 'base_options', 'resolved_base',
               'sprt', 'num_games', 'tc', 'threads', 'book', 'book_depth',
               'priority', 'username', 'tests_repo', 'info']:
    value = run['args'].get(name, '-')
    if name == 'sprt' and value != '-':
      value = 'elo0: %.2f alpha: %.2f elo1: %.2f beta: %.2f state: %s' % (value['elo0'], value['alpha'], value['elo1'], value['beta'], value.get('state', '-'))
    run_args.append((name, value))
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

    results = request.rundb.get_results(run)
    run['results_info'] = format_results(request.rundb, run)

    state = 'finished'

    if not run['finished']:
      for task in run['tasks']:
        if task['active']:
          state = 'active'
        elif task['pending'] and not state == 'active':
          state = 'pending'

      if state == 'finished':
        run['finished'] = True
        request.rundb.runs.save(run)

    if state == 'finished' and results['wins'] + results['losses'] + results['draws'] == 0:
      state = 'failed'

    runs[state].append(run)

  runs['pending'].sort(reverse=True, key=lambda run: (-run['args']['priority'], run['start_time']))
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
