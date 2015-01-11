import copy
import datetime
import numpy
import os
import scipy
import scipy.stats
import sys
import json
import smtplib
import requests
from email.mime.text import MIMEText
from collections import defaultdict
from pyramid.security import remember, forget, authenticated_userid, has_permission
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

@view_config(route_name='signup', renderer='signup.mak')
def signup(request):
  if 'form.submitted' in request.params:
    if len(request.params.get('password', '')) == 0:
      request.session.flash('Non-empty password required')
      return {}

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
      delta = 'seconds ago'
  else:
    delta = 'Never'
  return delta

def parse_tc(tc):
  # Total time for a game is assumed to be the double of tc for each player
  # reduced for 70% becuase on average game is stopped earlier. For instance
  # in case of 60+0.05 time for each player is 62 secs, so the game duration
  # is 62*2*70%
  scale = 2 * 0.90

  # Parse the time control in cutechess format
  if tc == '15+0.05':
    return 17.0 * scale

  if tc == '60+0.05':
    return 62.0 * scale

  chunks = tc.split('+')
  increment = 0.0
  if len(chunks) == 2:
    increment = float(chunks[1])

  chunks = chunks[0].split('/')
  num_moves = 0
  if len(chunks) == 2:
    num_moves = int(chunks[0])

  time_tc = chunks[-1]
  chunks = time_tc.split(':')
  if len(chunks) == 2:
    time_tc = float(chunks[0]) * 60 + float(chunks[1])
  else:
    time_tc = float(chunks[0])

  if num_moves > 0:
    time_tc = time_tc * (40.0 / num_moves)
  return (time_tc + (increment * 40.0)) * scale

@view_config(route_name='actions', renderer='actions.mak')
def actions(request):
  actions = []
  for action in request.actiondb.get_actions(100):
    item = {
      'action': action['action'],
      'time': action['time'],
      'username': action['username'],
    }
    if action['action'] == 'modify_run':
      item['run'] = action['data']['before']['args']['new_tag']
      item['_id'] = action['data']['before']['_id']
      item['description'] = []

      before = action['data']['before']['args']['priority']
      after = action['data']['after']['args']['priority']
      if before != after:
        item['description'].append('priority changed from %s to %s' % (before, after))

      before = action['data']['before']['args']['num_games']
      after = action['data']['after']['args']['num_games']
      if before != after:
        item['description'].append('games changed from %s to %s' % (before, after))

      item['description'] = 'modify: ' + ','.join(item['description'])
    else:
      item['run'] = action['data']['args']['new_tag']
      item['_id'] = action['data']['_id']
      item['description'] = ' '.join(action['action'].split('_'))
      if action['action'] == 'stop_run':
        item['description'] += ': %s' % (action['data'].get('stop_reason', 'User stop'))

    actions.append(item)

  return {'actions': actions}

@view_config(route_name='users', renderer='users.mak')
def users(request):
  users = list(request.userdb.user_cache.find())
  users.sort(key=lambda k: k['cpu_hours'], reverse=True)
  return {'users': users}

def get_sha(branch, repo_url):
  """Resolves the git branch to sha commit"""
  api_url = repo_url.replace('https://github.com', 'https://api.github.com/repos')
  commit = requests.get(api_url + '/commits/' + branch).json()
  if 'sha' in commit:
    return commit['sha'], commit['commit']['message'].split('\n')[0]
  else:
    return '', ''

def parse_spsa_params(raw, spsa):
  params = []
  for line in raw.split('\n'):
    chunks = line.strip().split(',')
    if len(chunks) == 0:
      continue
    if len(chunks) != 6:
      raise Exception('"%s" needs 6 parameters"' % (line))
    param = {
      'name': chunks[0],
      'start': float(chunks[1]),
      'min': float(chunks[2]),
      'max': float(chunks[3]),
      'c_end': float(chunks[4]),
      'r_end': float(chunks[5]),
    }
    param['c'] = param['c_end'] * spsa['num_iter'] ** spsa['gamma']
    param['a_end'] = param['r_end'] * param['c_end'] ** 2
    param['a'] = param['a_end'] * (spsa['A'] + spsa['num_iter']) ** spsa['alpha']
    param['theta'] = param['start']

    params.append(param)

  return params

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
    raise Exception('Missing required option')

  data['regression_test'] = request.POST['test_type'] == 'Regression'
  if data['regression_test']:
    data['base_tag'] = data['new_tag']
    data['base_signature'] = data['new_signature']
    data['base_options'] = data['new_options']

  # In case of reschedule use old data, otherwise resolve sha and update user's tests_repo
  if 'resolved_base' in request.POST:
    data['resolved_base'] = request.POST['resolved_base']
    data['resolved_new'] = request.POST['resolved_new']
    data['msg_base'] = request.POST['msg_base']
    data['msg_new'] = request.POST['msg_new']
  else:
    data['resolved_base'], data['msg_base'] = get_sha(data['base_tag'], data['tests_repo'])
    data['resolved_new'], data['msg_new'] = get_sha(data['new_tag'], data['tests_repo'])
    u = request.userdb.get_user(data['username'])
    if u.get('tests_repo', '') != data['tests_repo']:
      u['tests_repo'] = data['tests_repo']
      request.userdb.users.save(u)

  if len(data['resolved_base']) == 0 or len(data['resolved_new']) == 0:
    raise Exception('Unable to find branch!')

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
  elif stop_rule == 'spsa':
    data['num_games'] = int(request.POST['num-games'])
    if data['num_games'] <= 0:
      raise Exception('Number of games must be >= 0')

    data['spsa'] = {
      'A': int(request.POST['spsa_A']),
      'alpha': float(request.POST['spsa_alpha']),
      'gamma': float(request.POST['spsa_gamma']),
      'raw_params': request.POST['spsa_raw_params'],
      'iter': 0,
      'num_iter': int(data['num_games'] / 2),
    }
    data['spsa']['params'] = parse_spsa_params(request.POST['spsa_raw_params'], data['spsa'])
  else:
    data['num_games'] = int(request.POST['num-games'])
    if data['num_games'] <= 0:
      raise Exception('Number of games must be >= 0')

  data['threads'] = int(request.POST['threads'])
  data['priority'] = int(request.POST['priority'])

  if data['threads'] <= 0:
    raise Exception('Threads must be >= 1')

  # Optional
  data['info'] = request.POST['run-info']

  return data

@view_config(route_name='tests_run', renderer='tests_run.mak', permission='modify_db')
def tests_run(request):
  if 'base-branch' in request.POST:
    try:
      data = validate_form(request)
      run_id = request.rundb.new_run(**data)

      request.actiondb.new_run(authenticated_userid(request), request.rundb.get_run(run_id))
      request.session.flash('Started test run!')
      return HTTPFound(location=request.route_url('tests'))
    except Exception as e:
      request.session.flash(str(e))

  run_args = {}
  if 'id' in request.params:
    run_args = request.rundb.get_run(request.params['id'])['args']

  username = authenticated_userid(request)
  u = request.userdb.get_user(username)

  return { 'args': run_args, 'tests_repo': u.get('tests_repo', '') }

def can_modify_run(request, run):
  return run['args']['username'] == authenticated_userid(request) or has_permission('approve_run', request.context, request)

@view_config(route_name='tests_modify', permission='modify_db')
def tests_modify(request):
  if 'num-games' in request.POST:
    run = request.rundb.get_run(request.POST['run'])
    before = copy.deepcopy(run)

    if not can_modify_run(request, run):
      request.session.flash('Unable to modify another users run!')
      return HTTPFound(location=request.route_url('tests'))

    existing_games = 0
    for chunk in run['tasks']:
      existing_games += chunk['num_games']

    num_games = int(request.POST['num-games'])
    if num_games > run['args']['num_games'] and not ('sprt' in run['args'] or 'spsa' in run['args']):
      request.session.flash('Unable to modify number of games in a fixed game test!')
      return HTTPFound(location=request.route_url('tests'))

    if num_games > existing_games:
      # Create new chunks for the games
      new_chunks = request.rundb.generate_tasks(num_games - existing_games)
      run['tasks'] += new_chunks

    run['finished'] = False
    run['args']['num_games'] = num_games
    run['args']['priority'] = int(request.POST['priority'])
    request.rundb.runs.save(run)

    request.actiondb.modify_run(authenticated_userid(request), before, run)

    request.session.flash('Run successfully modified!')
    return HTTPFound(location=request.route_url('tests'))
  return {}

@view_config(route_name='tests_stop', permission='modify_db')
def tests_stop(request):
  run = request.rundb.get_run(request.POST['run-id'])
  if not can_modify_run(request, run):
    request.session.flash('Unable to modify another users run!')
    return HTTPFound(location=request.route_url('tests'))

  request.rundb.stop_run(request.POST['run-id'])

  run = request.rundb.get_run(request.POST['run-id'])
  request.actiondb.stop_run(authenticated_userid(request), run)

  request.session.flash('Stopped run')
  return HTTPFound(location=request.route_url('tests'))

@view_config(route_name='tests_approve', permission='approve_run')
def tests_approve(request):
  username = authenticated_userid(request)
  if not request.rundb.approve_run(request.POST['run-id'], username):
    request.session.flash('Unable to approve run!')
    return HTTPFound(location=request.route_url('tests'))

  run = request.rundb.get_run(request.POST['run-id'])
  request.actiondb.approve_run(username, run)

  request.session.flash('Approved run')
  return HTTPFound(location=request.route_url('tests'))

def purge_run(rundb, run):
  # Remove bad runs
  purged = False
  chi2 = calculate_residuals(run)
  if 'bad_tasks' not in run:
    run['bad_tasks'] = []
  for task in run['tasks']:
    if task['worker_key'] in chi2['bad_users']:
      purged = True
      run['bad_tasks'].append(task)
      if 'stats' in task:
        del task['stats']
      del task['worker_key']

  if purged:
    # Generate new tasks if needed
    run['results_stale'] = True
    results = rundb.get_results(run)
    played_games = results['wins'] + results['losses'] + results['draws']
    if played_games < run['args']['num_games']:
      run['tasks'] += rundb.generate_tasks(run['args']['num_games'] - played_games)

    run['finished'] = False
    if 'sprt' in run['args'] and 'state' in run['args']['sprt']:
      del run['args']['sprt']['state']
    
    rundb.runs.save(run)

  return purged 

@view_config(route_name='tests_purge', permission='approve_run')
def tests_purge(request):
  username = authenticated_userid(request)

  run = request.rundb.get_run(request.POST['run-id'])
  if not run['finished']:
    request.session.flash('Can only purge completed run')
    return HTTPFound(location=request.route_url('tests'))

  purged = purge_run(request.rundb, run)
  if not purged:
    request.session.flash('No bad workers!')
    return HTTPFound(location=request.route_url('tests'))

  request.actiondb.purge_run(username, run)

  request.session.flash('Purged run')
  return HTTPFound(location=request.route_url('tests'))

@view_config(route_name='tests_delete', permission='modify_db')
def tests_delete(request):
  run = request.rundb.get_run(request.POST['run-id'])
  if not can_modify_run(request, run):
    request.session.flash('Unable to modify another users run!')
    return HTTPFound(location=request.route_url('tests'))

  run['deleted'] = True
  run['finished'] = True
  for w in run['tasks']:
    w['pending'] = False
  request.rundb.runs.save(run)

  request.actiondb.delete_run(authenticated_userid(request), run)

  request.session.flash('Deleted run')
  return HTTPFound(location=request.route_url('tests'))

def format_results(run_results, run):
  result = {'style': '', 'info': []}

  # win/loss/draw count
  WLD = [run_results['wins'], run_results['losses'], run_results['draws']]

  if 'spsa' in run['args']:
    result['info'].append('%d/%d iterations' % (run['args']['spsa']['iter'], run['args']['spsa']['num_iter']))
    result['info'].append('%d/%d games played' % (WLD[0] + WLD[1] + WLD[2], run['args']['num_games']))
    return result

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
    result['info'].append('LLR: %.2f (%.2lf,%.2lf) [%.2f,%.2f]' % (stats['llr'], stats['lower_bound'], stats['upper_bound'], sprt['elo0'], sprt['elo1']))
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
    if WLD[0] > WLD[1]:
      result['style'] = 'yellow'
    else:
      result['style'] = '#FF6A6A'
  elif state == 'accepted':
    result['style'] = '#44EB44'
  return result

def get_worker_key(task):
  if 'worker_info' not in task:
    return '-'
  return '%s-%scores' % (task['worker_info'].get('username', ''), str(task['worker_info']['concurrency']))

def get_chi2(tasks, bad_users):
  """Perform chi^2 test on the stats from each worker"""
  results = {'chi2': 0.0, 'dof': 0, 'p': 0.0, 'residual': {}}

  # Aggregate results by worker
  users = {}
  for task in tasks:
    task['worker_key'] = get_worker_key(task)
    if 'worker_info' not in task:
      continue
    key = get_worker_key(task)
    if key in bad_users:
      continue
    stats = task.get('stats', {})
    wld = [float(stats.get('wins', 0)), float(stats.get('losses', 0)), float(stats.get('draws', 0))]
    if wld == [0.0, 0.0, 0.0]:
      continue
    if key in users:
      for idx in range(len(wld)):
        users[key][idx] += wld[idx]
    else:
      users[key] = wld

  if len(users) == 0:
    return results

  observed = numpy.array(users.values())
  rows,columns = observed.shape
  df = (rows - 1) * (columns - 1)
  column_sums = numpy.sum(observed, axis=0)
  row_sums = numpy.sum(observed, axis=1)
  grand_total = numpy.sum(column_sums)
  if grand_total == 0:
    return results

  expected = numpy.outer(row_sums, column_sums) / grand_total
  diff = observed - expected
  adj = numpy.outer((1 - row_sums / grand_total), (1 - column_sums / grand_total))
  residual = diff / numpy.sqrt(expected * adj)
  for idx in range(len(users)):
    users[users.keys()[idx]] = numpy.max(numpy.abs(residual[idx]))
  chi2 = numpy.sum(diff * diff / expected)
  return {
    'chi2': chi2,
    'dof': df,
    'p': 1 - scipy.stats.chi2.cdf(chi2, df),
    'residual': users,
  }

def calculate_residuals(run):
  bad_users = set()
  chi2 = get_chi2(run['tasks'], bad_users)
  residuals = chi2['residual']

  # Limit bad users to 1 for now
  for _ in range(1):
    worst_user = {}
    for task in run['tasks']:
      if task['worker_key'] in bad_users:
        continue
      task['residual'] = residuals.get(task['worker_key'], 0.0)

      # Special case crashes or time losses
      stats = task.get('stats', {})
      crashes = stats.get('crashes', 0)
      time_losses = stats.get('time_losses', 0)
      if crashes > 1 or time_losses > 1:
        task['residual'] = 8.0

      if abs(task['residual']) < 2.0:
        task['residual_color'] = '#44EB44'
      elif abs(task['residual']) < 2.7:
        task['residual_color'] = 'yellow'
      else:
        task['residual_color'] = '#FF6A6A'

      if chi2['p'] < 0.05 or task['residual'] > 7.0:
        if len(worst_user) == 0 or task['residual'] > worst_user['residual']:
          worst_user['worker_key'] = task['worker_key']
          worst_user['residual'] = task['residual']

    if len(worst_user) == 0:
      break
    bad_users.add(worst_user['worker_key'])
    residuals = get_chi2(run['tasks'], bad_users)['residual']

  chi2['bad_users'] = bad_users
  return chi2

@view_config(route_name='tests_view_spsa_history', renderer='json')
def tests_view_spsa_history(request):
  run = request.rundb.get_run(request.matchdict['id'])
  if 'spsa' not in run['args']:
    return {}

  return run['args']['spsa']

@view_config(route_name='tests_view', renderer='tests_view.mak')
def tests_view(request):
  run = request.rundb.get_run(request.matchdict['id'])
  results = request.rundb.get_results(run)
  run['results_info'] = format_results(results, run)
  run_args = [('id', str(run['_id']), '')]

  for name in ['new_tag', 'new_signature', 'new_options', 'resolved_new',
               'base_tag', 'base_signature', 'base_options', 'resolved_base',
               'sprt', 'num_games', 'spsa', 'tc', 'threads', 'book', 'book_depth',
               'priority', 'username', 'tests_repo', 'info']:

    if not name in run['args']:
      continue

    value = run['args'][name]
    url = ''

    if name == 'new_tag' and 'msg_new' in run['args']:
      value += '  (' + run['args']['msg_new'][:50] + ')'

    if name == 'base_tag' and 'msg_base' in run['args']:
      value += '  (' + run['args']['msg_base'][:50] + ')'

    if name == 'sprt' and value != '-':
      value = 'elo0: %.2f alpha: %.2f elo1: %.2f beta: %.2f state: %s' % \
              (value['elo0'], value['alpha'], value['elo1'], value['beta'], value.get('state', '-'))

    if name == 'spsa' and value != '-':
      params = ['param: %s, best: %.2f, start: %.2f, min: %.2f, max: %.2f, c %f, a %f' % \
                (p['name'], p['theta'], p['start'], p['min'], p['max'], p['c'], p['a']) for p in value['params']]
      value = 'Iter: %d, A: %d, alpha %f, gamma %f\n%s' % (value['iter'], value['A'], value['alpha'], value['gamma'], '\n'.join(params))

    if 'tests_repo' in run['args']:
      if name == 'new_tag':
        url = run['args']['tests_repo'] + '/commit/' + run['args']['resolved_new']
      elif name == 'base_tag':
        url = run['args']['tests_repo'] + '/commit/' + run['args']['resolved_base']
      elif name == 'tests_repo' :
        url = value

    try:
      strval = str(value)
    except:
      strval = value.encode('ascii', 'replace')
    run_args.append((name, strval, url))

  for task in run['tasks']:
    last_updated = task.get('last_updated', datetime.datetime.min)
    task['last_updated'] = delta_date(last_updated)

  return { 'run': run, 'run_args': run_args, 'chi2': calculate_residuals(run)}

def post_result(run):
  title = run['args']['new_tag'][:23]

  if 'username' in run['args']:
    title += '  (' + run['args']['username'] + ')'

  body = 'http://tests.stockfishchess.org/tests/view/%s\n\n' % (str(run['_id']))

  body += run['start_time'].strftime("%d-%m-%y") + ' from '
  body += run['args'].get('username','') + '\n\n'

  body += run['args']['new_tag'] + ': ' + run['args'].get('msg_new', '') + '\n'
  body += run['args']['base_tag'] + ': ' + run['args'].get('msg_base', '') + '\n\n'

  body += 'TC: ' + run['args']['tc'] + ' th ' + str(run['args'].get('threads',1)) + '\n'
  body += '\n'.join(run['results_info']['info']) + '\n\n'

  body += run['args'].get('info', '') + '\n\n'

  msg = MIMEText(body)
  msg['Subject'] = title
  msg['From'] = 'fishtest@noreply.github.com'
  msg['To'] = 'fishcooking_results@googlegroups.com'

  s = smtplib.SMTP('localhost')
  s.sendmail(msg['From'], [msg['To']], msg.as_string())
  s.quit()

@view_config(route_name='tests', renderer='tests.mak')
@view_config(route_name='tests_user', renderer='tests.mak')
def tests(request):
  username = request.matchdict.get('username', '')

  runs = { 'pending':[], 'failed':[], 'active':[], 'finished':[] }

  unfinished_runs = request.rundb.get_unfinished_runs()
  for run in unfinished_runs:
    if len(username) > 0 and run['args'].get('username', '') != username:
      continue

    results = request.rundb.get_results(run)
    run['results_info'] = format_results(results, run)

    state = 'finished'

    for task in run['tasks']:
      if task['active']:
        state = 'active'
      elif task['pending'] and not state == 'active':
        state = 'pending'

    if state == 'finished':
      purged = 0
      while purge_run(request.rundb, run) and purged < 5:
        purged += 1
        run = request.rundb.get_run(run['_id'])

        results = request.rundb.get_results(run)
        run['results_info'] = format_results(results, run)

      if purged == 0:
        run['finished'] = True
        request.rundb.runs.save(run)
        post_result(run)

    runs[state].append(run)

  runs['pending'].sort(reverse=True, key=lambda run: (-run['args']['priority'], run['start_time']))

  games_per_minute = 0.0
  machines = request.rundb.get_machines()
  for machine in machines:
    machine['last_updated'] = delta_date(machine['last_updated'])
    if machine['nps'] != 0:
      games_per_minute += (machine['nps'] / 1200000.0) * (60.0 / parse_tc(machine['run']['args']['tc'])) * int(machine['concurrency'])
  machines.reverse()

  def remaining_hours(run):
    r = run['results']
    expected_games = run['args']['num_games']
    if 'sprt' in run['args']:
      expected_games = 16000
    remaining_games = max(0, expected_games - r['wins'] - r['losses'] - r['draws'])
    game_secs = parse_tc(run['args']['tc'])
    return game_secs * remaining_games * int(run['args'].get('threads', 1)) / (60*60)

  cores = sum([int(m['concurrency']) for m in machines])
  nps = sum([int(m['concurrency']) * m['nps'] for m in machines])
  if cores > 0:
    pending_hours = 0
    for run in runs['pending'] + runs['active']:
      eta = remaining_hours(run) / cores
      pending_hours += eta
      info = run['results_info']
      if 'Pending...' in info['info']:
        info['info'][0] += ' (%.1f hrs)' % (eta)
        if 'binaries_url' in run:
          info['info'][0] += ' (+bin)'

  else:
    pending_hours = 0

  def total_games(run):
    res = run['results']
    return res['wins'] + res['draws'] + res['losses']
  games_played = sum([total_games(r) for r in runs['finished']])

  # Pagination
  page = max(0, int(request.params.get('page', 1)) - 1)
  page_size = 50
  finished, num_finished = request.rundb.get_finished_runs(skip=page*page_size, limit=page_size, username=username)
  runs['finished'] += finished

  for run in finished:
    results = request.rundb.get_results(run)
    if results['wins'] + results['losses'] + results['draws'] == 0:
      runs['failed'].append(run)

  runs['finished'] = [r for r in runs['finished'] if r not in runs['failed']]

  pages = [{'idx': 'Prev', 'url': '?page=%d' % (page), 'state': 'disabled' if page == 0 else ''}]
  for idx, page_idx in enumerate(range(0, num_finished, page_size)):
    pages.append({'idx': idx + 1, 'url': '?page=%d' % (idx + 1), 'state': 'active' if page == idx else ''})
  pages.append({'idx': 'Next', 'url': '?page=%d' % (page + 2), 'state': 'disabled' if page + 1 == len(pages) - 1 else ''})

  return {
    'runs': runs,
    'finished_runs': num_finished,
    'page_idx': page,
    'pages': pages,
    'machines': machines,
    'show_machines': len(username) == 0,
    'pending_hours': '%.1f' % (pending_hours),
    'games_played': games_played,
    'cores': cores,
    'nps': nps,
    'games_per_minute': int(games_per_minute),
  }
