import json, sys
import clop
import requests
from pyramid.view import view_config

FLAG_HOST = 'http://freegeoip.net/json/'

def authenticate(request):
  if 'username' in request.json_body: username = request.json_body['username']
  else: username = request.json_body['worker_info']['username']
  return request.userdb.authenticate(username, request.json_body['password'])

@view_config(route_name='api_request_task', renderer='string')
def request_task(request):
  token = authenticate(request)
  if 'error' in token: return json.dumps(token)

  worker_info = request.json_body['worker_info']
  worker_info['remote_addr'] = request.remote_addr

  # Get country flag ip
  try:
    r = requests.get(FLAG_HOST + request.remote_addr, timeout=1.0)
    if r.status_code == 200:
      worker_info['country_code'] = r.json().get('country_code', '')
  except:
    pass

  result = request.rundb.request_task(worker_info)

  if 'task_waiting' in result:
    return json.dumps(result)

  # Strip the run of unneccesary information
  run = result['run']
  min_run = {
    '_id': str(run['_id']),
    'args': run['args'],
    'tasks': [],
    'binaries_url': run.get('binaries_url', ''),
  }

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
    clop=request.json_body.get('clop', []),
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

@view_config(route_name='api_stop_run', renderer='string')
def stop_run(request):
  token = authenticate(request)
  if 'error' in token: return json.dumps(token)

  result = request.rundb.stop_run(request.json_body['run_id'])
  return json.dumps(result)

@view_config(route_name='api_request_build', renderer='string')
def request_build(request):
  token = authenticate(request)
  if 'error' in token: return json.dumps(token)

  run = request.rundb.get_run_to_build()
  if run == None:
    return json.dumps({'no_run': True})

  min_run = {
    'run_id': str(run['_id']),
    'args': run['args'],
  }
  return json.dumps(min_run)

@view_config(route_name='api_build_ready', renderer='string')
def build_ready(request):
  token = authenticate(request)
  if 'error' in token: return json.dumps(token)

  run = request.rundb.get_run(request.json_body['run_id'])
  if run == None:
    return json.dumps({'ok': False})

  run['binaries_url'] = request.json_body['binaries_url']
  request.rundb.runs.save(run)
  return json.dumps({'ok': True})

@view_config(route_name='api_request_version', renderer='string')
def request_version(request):
  token = authenticate(request)
  if 'error' in token: return json.dumps(token)

  return json.dumps({'version': 46})

@view_config(route_name='api_request_clop', renderer='string')
def request_clop(request):
  token = authenticate(request)
  if 'error' in token: return json.dumps(token)

  run_id = request.json_body['run_id']
  task_id = int(request.json_body['task_id'])

  return json.dumps(request.clopdb.request_game(run_id, task_id))
