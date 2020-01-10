import json, sys
import base64
import requests
import pyramid.httpexceptions as exc
from pyramid.view import view_config
import fishtest.stats.sprt

def get_flag(request):
  ip = request.remote_addr
  result = request.userdb.flag_cache.find_one({'ip': ip})
  if result != None:
    return result['country_code']

  # Get country flag ip
  try:
    FLAG_HOST = 'https://freegeoip.app/json/'

    r = requests.get(FLAG_HOST + request.remote_addr, timeout=1.0)
    if r.status_code == 200:
      country_code = r.json()['country_code']

      request.userdb.flag_cache.insert({
        'ip': ip,
        'country_code': country_code
      })

      return country_code
  except:
    return None

def get_username(request):
  if 'username' in request.json_body: return request.json_body['username']
  return request.json_body['worker_info']['username']

def authenticate(request):
  return request.userdb.authenticate(get_username(request), request.json_body['password'])

def strip_run(run):
  if 'tasks' in run:
    del run['tasks']
  if 'bad_tasks' in run:
    del run['bad_tasks']
  if 'spsa' in run['args'] and 'param_history' in run['args']['spsa']:
    del run['args']['spsa']['param_history']
  run['_id'] = str(run['_id'])
  run['start_time'] = str(run['start_time'])
  run['last_updated'] = str(run['last_updated'])
  return run

@view_config(route_name='api_active_runs', renderer='string')
def active_runs(request):
  l = {}
  for run in request.rundb.get_unfinished_runs():
    l[run['_id']] = strip_run(run)
  return json.dumps(l)

@view_config(route_name='api_get_run', renderer='string')
def get_run(request):
  run = request.rundb.get_run(request.matchdict['id'])
  return json.dumps(strip_run(run.copy()))

@view_config(route_name='api_get_elo', renderer='string')
def get_elo(request):
  run = request.rundb.get_run(request.matchdict['id']).copy()
  results=run['results']
  if 'sprt' not in run['args']:
    return json.dumps({})
  sprt=run['args'].get('sprt').copy()
  elo_model=sprt.get('elo_model','BayesElo')
  alpha=sprt['alpha']
  beta=sprt['beta']
  elo0=sprt['elo0']
  elo1=sprt['elo1']
  sprt['elo_model']=elo_model
  p=0.05
  a=fishtest.stats.stat_util.SPRT_elo(results,alpha=alpha,beta=beta,elo0=elo0,elo1=elo1,elo_model=elo_model)
  run=strip_run(run)
  run['elo']=a
  run['args']['sprt']=sprt
  return json.dumps(run)

@view_config(route_name='api_request_task', renderer='string')
def request_task(request):
  token = authenticate(request)
  if 'error' in token: return json.dumps(token)

  worker_info = request.json_body['worker_info']
  worker_info['remote_addr'] = request.remote_addr
  flag = get_flag(request)
  if flag:
    worker_info['country_code'] = flag

  result = request.rundb.request_task(worker_info)

  if 'task_waiting' in result:
    return json.dumps(result)

  # Strip the run of unneccesary information
  run = result['run']
  min_run = {
    '_id': str(run['_id']),
    'args': run['args'],
    'tasks': [],
  }

  if int(str(worker_info['version']).split(':')[0]) > 64:
    task = run['tasks'][result['task_id']]
    min_task = {'num_games': task['num_games']}
    if 'stats' in task:
      min_task['stats'] = task['stats']
    min_run['my_task'] = min_task
  else:
    for task in run['tasks']:
      min_task = {'num_games': task['num_games']}
      if 'stats' in task:
        min_task['stats'] = task['stats']
      min_run['tasks'].append(min_task)

  result['run'] = min_run
  return json.dumps(result)

@view_config(route_name='api_update_task', renderer='string')
def update_task(request):
  token = authenticate(request)
  if 'error' in token: return json.dumps(token)

  result = request.rundb.update_task(
    run_id=request.json_body['run_id'],
    task_id=int(request.json_body['task_id']),
    stats=request.json_body['stats'],
    nps=request.json_body.get('nps', 0),
    spsa=request.json_body.get('spsa', {}),
    username=get_username(request)
  )
  return json.dumps(result)

@view_config(route_name='api_failed_task', renderer='string')
def failed_task(request):
  token = authenticate(request)
  if 'error' in token: return json.dumps(token)

  result = request.rundb.failed_task(
    run_id=request.json_body['run_id'],
    task_id=int(request.json_body['task_id']),
  )
  return json.dumps(result)

@view_config(route_name='api_upload_pgn', renderer='string')
def upload_pgn(request):
  token = authenticate(request)
  if 'error' in token: return json.dumps(token)

  result = request.rundb.upload_pgn(
    run_id=request.json_body['run_id'] + '-' + str(request.json_body['task_id']),
    pgn_zip=base64.b64decode(request.json_body['pgn'])
  )
  return json.dumps(result)

@view_config(route_name='api_download_pgn', renderer='string')
def download_pgn(request):
  pgn = request.rundb.get_pgn(request.matchdict['id'])
  if pgn == None:
    raise exc.exception_response(404)
  if '.pgn' in request.matchdict['id']:
    request.response.content_type = 'application/x-chess-pgn'
  return pgn

@view_config(route_name='api_download_pgn_100', renderer='string')
def download_pgn_100(request):
  skip = int(request.matchdict['skip'])
  urls = request.rundb.get_pgn_100(skip)
  if urls == None:
    raise exc.exception_response(404)
  return json.dumps(urls)

@view_config(route_name='api_stop_run', renderer='string')
def stop_run(request):
  token = authenticate(request)
  if 'error' in token: return json.dumps(token)

  username = get_username(request)
  user = request.userdb.user_cache.find_one({'username': username})
  if not user or user['cpu_hours'] < 1000:
    return ''

  with request.rundb.active_run_lock(str(request.json_body['run_id'])):
    run = request.rundb.get_run(request.json_body['run_id'])
    run['finished'] = True
    run['stop_reason'] = request.json_body.get('message', 'API request')
    request.actiondb.stop_run(username, run)

    result = request.rundb.stop_run(request.json_body['run_id'])
  return json.dumps(result)

@view_config(route_name='api_request_version', renderer='string')
def request_version(request):
  token = authenticate(request)
  if 'error' in token: return json.dumps(token)

  return json.dumps({'version': 71})

@view_config(route_name='api_request_spsa', renderer='string')
def request_spsa(request):
  token = authenticate(request)
  if 'error' in token: return json.dumps(token)

  run_id = request.json_body['run_id']
  task_id = int(request.json_body['task_id'])

  return json.dumps(request.rundb.request_spsa(run_id, task_id))
