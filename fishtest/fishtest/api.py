import json, sys, os, requests
from PIL import Image
from StringIO import StringIO
from bson import json_util
from pyramid.view import view_config

FLAG_HOST='http://api.hostip.info/flag.php?ip='

def authenticate(request):
  if 'username' in request.json_body: username = request.json_body['username']
  else: username = request.json_body['worker_info']['username']
  return request.userdb.authenticate(username, request.json_body['password'])

def add_flag(request):
  flags_dir = os.path.dirname(os.path.realpath(__file__))
  flags_dir = os.path.join(flags_dir, 'flags')
  if not os.path.exists(flags_dir):
    os.makedirs(flags_dir)

  username = request.json_body['worker_info']['username']
  flag_file = os.path.join(flags_dir, username + '.gif')
  if os.path.exists(flag_file):
    return

  flag = Image.open(StringIO(requests.get(FLAG_HOST + request.remote_addr).content))
  new_size = (flag.size[0] / 4, flag.size[1] / 4)
  flag = flag.resize(new_size, Image.ANTIALIAS)
  flag.save(flag_file)

@view_config(route_name='api_request_task', renderer='string')
def request_task(request):
  token = authenticate(request)
  if 'error' in token: return json.dumps(token)

  add_flag(request)
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

@view_config(route_name='api_request_version', renderer='string')
def request_version(request):
  token = authenticate(request)
  if 'error' in token: return json.dumps(token)

  return json.dumps({'version': '7'})
