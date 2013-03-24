import json, sys
from bson import json_util
from pyramid.view import view_config

def authenticate(request):
  if 'username' in request.json_body: username = request.json_body['username']
  else: username = request.json_body['worker_info']['username']
  return request.userdb.authenticate(username, request.json_body['password'])

@view_config(route_name='api_request_task', renderer='string')
def request_task(request):
  token = authenticate(request)
  if 'error' in token: return json.dumps(token)

  task = request.rundb.request_task(request.json_body['worker_info'])
  return json.dumps(task, default=json_util.default)

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

  return json.dumps({'version': '8'})
