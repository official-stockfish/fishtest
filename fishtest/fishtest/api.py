import json
from bson import json_util
from pyramid.view import view_config

from .security import USERS

@view_config(route_name='api_request_task', renderer='string')
def request_task(request):
  """Assign the highest priority task to the worker"""
  worker_info = request.json_body['worker_info']
  username = worker_info['username']
  password = request.json_body['password']
  if USERS.get(username) != password:
    return json.dumps({'error': 'Invalid password'})

  # Does this worker have a task already?  If so, just hand that back
  existing_task = request.rundb.runs.find_one({'tasks': {'$elemMatch': {'active': True, 'worker_info': worker_info}}})
  if existing_task != None:
    for task in existing_task['tasks']:
      if task['active'] and task['worker_info'] == worker_info:
        return json.dumps(task, default=json_util.default) 

  task = request.rundb.request_task(worker_info)
  return json.dumps(task, default=json_util.default)

@view_config(route_name='api_update_task', renderer='string')
def update_task(request):
  username = request.json_body['username']
  password = request.json_body['password']
  if USERS.get(username) != password:
    return json.dumps({'error': 'Invalid password'})

  result = request.rundb.update_task(
    run_id=request.json_body['run_id'],
    task_id=int(request.json_body['task_id']),
    stats=request.json_body['stats'],
  )
  return json.dumps(result)

@view_config(route_name='api_failed_task', renderer='string')
def failed_task(request):
  username = request.json_body['username']
  password = request.json_body['password']
  if USERS.get(username) != password:
    return json.dumps({'error': 'Invalid password'})

  result = request.rundb.failed_task(
    run_id=request.json_body['run_id'],
    task_id=int(request.json_body['task_id']),
  )
  return json.dumps(result)
