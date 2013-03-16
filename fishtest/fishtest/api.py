import json, sys
from bson import json_util
from pyramid.view import view_config

from .security import USERS

def invalid_password(request):
  if 'username' in request.json_body: username = request.json_body['username']
  else: username = request.json_body['worker_info']['username']
  password = request.json_body['password']
  if USERS.get(username) != password:
    sys.stderr.write('Invalid login: "%s" "%s"\n' % (username, password))
    return True
  return False

@view_config(route_name='api_request_task', renderer='string')
def request_task(request):
  if invalid_password(request):
    return json.dumps({'error': 'Invalid password'})

  worker_info = request.json_body['worker_info']
  task = request.rundb.request_task(worker_info)
  return json.dumps(task, default=json_util.default)

@view_config(route_name='api_update_task', renderer='string')
def update_task(request):
  if invalid_password(request):
    return json.dumps({'error': 'Invalid password'})

  result = request.rundb.update_task(
    run_id=request.json_body['run_id'],
    task_id=int(request.json_body['task_id']),
    stats=request.json_body['stats'],
  )
  return json.dumps(result)

@view_config(route_name='api_failed_task', renderer='string')
def failed_task(request):
  if invalid_password(request):
    return json.dumps({'error': 'Invalid password'})

  result = request.rundb.failed_task(
    run_id=request.json_body['run_id'],
    task_id=int(request.json_body['task_id']),
  )
  return json.dumps(result)

@view_config(route_name='api_request_version', renderer='string')
def request_version(request):
  if invalid_password(request):
    return json.dumps({'error': 'Invalid password'})

  return json.dumps({'version': '001'})
