import json, sys
import clop
from pyramid.view import view_config

from builder import get_binary_url

def authenticate(request):
  if 'username' in request.json_body: username = request.json_body['username']
  else: username = request.json_body['worker_info']['username']
  return request.userdb.authenticate(username, request.json_body['password'])

@view_config(route_name='api_request_task', renderer='string')
def request_task(request):
  token = authenticate(request)
  if 'error' in token: return json.dumps(token)

  worker_info = request.json_body['worker_info']
  result = request.rundb.request_task(worker_info)

  if 'task_waiting' in result:
    return json.dumps(result)

  # Strip the run of unneccesary information
  run = result['run']
  min_run = {
    '_id': str(run['_id']),
    'args': run['args'],
    'tasks': [],
    'new_engine_url': '',
    'base_engine_url': '',
  }

  # If is the start of a CLOP tuning session start CLOP
  if 'clop' in run['args'] and result['task_id'] == 0:
    clop.start_clop(str(run['_id']),
                    run['args']['new_tag'],
                    run['args']['clop']['params'])

  # Check if we have a binary to feed
  binaries_dir = run.get('binaries_dir', '')
  if len(binaries_dir) > 0:
    new_sha = run['args']['resolved_new']
    base_sha = run['args']['resolved_base']
    min_run['new_engine_url'] = get_binary_url(new_sha, binaries_dir, worker_info)
    min_run['base_engine_url'] = get_binary_url(base_sha, binaries_dir, worker_info)

    # Or both are set or none: avoid artifacts due to different compiles
    if min_run['new_engine_url'] == '' or min_run['base_engine_url'] == '':
      min_run['new_engine_url'] = ''
      min_run['base_engine_url'] = ''

    # TODO Disable at the moment
    print 'new_engine_url %s' % (min_run['new_engine_url'])
    print 'base_engine_url %s' % (min_run['base_engine_url'])
    min_run['new_engine_url'] = ''
    min_run['base_engine_url'] = ''

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
    game_id=request.json_body.get('game_id', ''),
    stats=request.json_body['stats'],
    nps=request.json_body.get('nps', 0),
    game_result=request.json_body.get('game_result', 'stop'),
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

  return json.dumps({'version': 19})
