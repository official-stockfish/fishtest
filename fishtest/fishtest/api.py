def request_task(request):
  """Assign the highest priority task to the worker"""
  task = request.rundb.request_task()
  return {}

def update_task(request):
  params = {}
  for key in [ 'id', 'task_id', 'wins', 'losses', 'draws' ]:
    params[key] = request.params[key]
  request.rundb.update_task(**params) 
