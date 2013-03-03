import json
from bson import json_util
from pyramid.view import view_config

@view_config(route_name='api_request_task', renderer='string')
def request_task(request):
  """Assign the highest priority task to the worker"""
  worker_info = request.json_body['worker_info']
  task = request.rundb.request_task(worker_info)
  return json.dumps(task, default=json_util.default)

@view_config(route_name='api_update_task')
def update_task(request):
  params = {}
  for key in [ 'run_id', 'task_id', 'stats' ]:
    params[key] = request.params[key]
  request.rundb.update_task(**params) 
