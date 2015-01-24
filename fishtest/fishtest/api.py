import json, sys
import requests
from pyramid.view import view_config

def get_flag(request):
  ip = request.remote_addr
  result = request.userdb.flag_cache.find_one({'ip': ip})
  if result != None:
    return result['country_code']

  # Get country flag ip
  try:
    #FLAG_HOST = 'http://freegeoip.net/json/'
    FLAG_HOST = 'http://geoip.nekudo.com/api/'

    r = requests.get(FLAG_HOST + request.remote_addr, timeout=1.0)
    if r.status_code == 200:
      country_code = r.json()['country']['code']

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
    spsa=request.json_body.get('spsa', {}),
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
  return {}

  # Stop run disabled until can be done more securely
  """
  token = authenticate(request)
  if 'error' in token: return json.dumps(token)

  run = request.rundb.get_run(request.json_body['run_id'])
  run['stop_reason'] = request.json_body.get('message', 'No reason!')
  request.actiondb.stop_run(get_username(request), run)

  result = request.rundb.stop_run(request.json_body['run_id'])
  return json.dumps(result)
  """

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

  return json.dumps({'version': 55})

@view_config(route_name='api_request_spsa', renderer='string')
def request_spsa(request):
  token = authenticate(request)
  if 'error' in token: return json.dumps(token)

  run_id = request.json_body['run_id']
  task_id = int(request.json_body['task_id'])

  return json.dumps(request.rundb.request_spsa(run_id, task_id))
