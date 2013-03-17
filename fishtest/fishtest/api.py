import json, sys
from bson import json_util
from pyramid.view import view_config

@view_config(route_name='api_request_task', renderer='string')
def request_task(request):
  """Assign the highest priority task to the worker"""
  worker_info = request.json_body['worker_info']
  token = request.userdb.authenticate(worker_info['username'], request.json_body['password'])
  if 'error' in token:
    return json.dumps(token)

@view_config(route_name='api_request_task', renderer='string')
def request_task(request):
  if invalid_password(request): return json.dumps({'error': 'Invalid password'})

  worker_info = request.json_body['worker_info']
  task = request.rundb.request_task(worker_info)
  return json.dumps(task, default=json_util.default)

@view_config(route_name='api_update_task', renderer='string')
def update_task(request):
  token = request.userdb.authenticate(request.json_body['username'], request.json_body['password'])
  if 'error' in token:
    return json.dumps(token)

  result = request.rundb.update_task(
    run_id=request.json_body['run_id'],
    task_id=int(request.json_body['task_id']),
    stats=request.json_body['stats'],
  )
  return json.dumps(result)

@view_config(route_name='api_failed_task', renderer='string')
def failed_task(request):
  token = request.userdb.authenticate(request.json_body['username'], request.json_body['password'])
  if 'error' in token:
    return json.dumps(token)

  result = request.rundb.failed_task(
    run_id=request.json_body['run_id'],
    task_id=int(request.json_body['task_id']),
  )
  return json.dumps(result)

@view_config(route_name='api_request_version', renderer='string')
def request_version(request):
  token = request.userdb.authenticate(request.json_body['username'], request.json_body['password'])
  if 'error' in token:
    return json.dumps(token)

  return json.dumps({'version': '2'})
