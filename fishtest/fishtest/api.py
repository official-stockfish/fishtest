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

  # Get country flag ip
  r = requests.get(FLAG_HOST + request.remote_addr)
  if r.status_code == 200:
    worker_info['country_code'] = r.json().get('country_code', '')

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

  # If is the start of a CLOP tuning session start CLOP. To check we are starting
  # a new CLOP run, check if there is only one active task in the run (the one
  # we are returning now.
  if 'clop' in run['args']:
    active_tasks = sum(t['active'] for t in run['tasks'])
    if active_tasks == 1:
      clop.start_clop(str(run['_id']), run['args']['new_tag'], run['args']['clop']['params'])

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

  return json.dumps({'version': 28})
