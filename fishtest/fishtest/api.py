def request_task(request):
  """Assign the highest priority task to the worker"""
  task = request.rundb.request_task(request.params['worker_info'])
  return task

def update_task(request):
  params = {}
  for key in [ 'run_id', 'task_id', 'stats' ]:
    params[key] = request.params[key]
  request.rundb.update_task(**params) 
