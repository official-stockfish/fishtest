import json, sys
from pyramid.view import view_config

def authenticate(request):
  if 'username' in request.json_body: username = request.json_body['username']
  else: username = request.json_body['worker_info']['username']
  return request.userdb.authenticate(username, request.json_body['password'])

@view_config(route_name='api_request_task', renderer='string')
def request_task(request):
  token = authenticate(request)
  if 'error' in token: return json.dumps(token)

  result = request.rundb.request_task(request.json_body['worker_info'])

  if 'task_waiting' in result:
    return json.dumps(result)

  # Strip the run of unneccesary information
  run = result['run']
  min_run = {
    '_id': str(run['_id']),
    'args': run['args'],
    'tasks': [],
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
   
@view_config(route_name='api_request_version', renderer='string')
def request_version(request):
  token = authenticate(request)
  if 'error' in token: return json.dumps(token)

  return json.dumps({'version': 10})
