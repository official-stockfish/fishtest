#!/usr/bin/python
import json
import os
import platform
import signal
import sys
import requests
import time
import traceback
from bson import json_util
from optparse import OptionParser
from games import run_games
from updater import update

WORKER_VERSION = 7
ALIVE = True

def on_sigint(signal, frame):
  global ALIVE
  ALIVE = False

def worker(worker_info, password, remote):
  payload = {
    'worker_info': worker_info,
    'password': password,
  }

  try:
    req = requests.post(remote + '/api/request_version', data=json.dumps(payload))
    req = json.loads(req.text, object_hook=json_util.object_hook)

    if int(req['version']) > WORKER_VERSION:
      print 'Updating worker version to %d' % (int(req['version']))
      update()

    req = requests.post(remote + '/api/request_task', data=json.dumps(payload))
    req = json.loads(req.text, object_hook=json_util.object_hook)
  except:
    sys.stderr.write('Exception accessing host:\n')
    traceback.print_exc()
    time.sleep(10)
    return

  if 'error' in req:
    raise Exception('Error from remote: %s' % (req['error']))

  # No tasks ready for us yet, just wait...
  if 'task_waiting' in req:
    time.sleep(10)
    return

  run, task_id = req['run'], req['task_id']
  try:
    run_games(worker_info, password, remote, run, task_id)
  except:
    sys.stderr.write('\nException running games:\n')
    traceback.print_exc()
    time.sleep(10)
  finally:
    payload = {
      'username': worker_info['username'],
      'password': password,
      'run_id': str(run['_id']),
      'task_id': task_id
    }
    requests.post(remote + '/api/failed_task', data=json.dumps(payload))
    sys.stderr.write('Task exited\n')

def main():
  signal.signal(signal.SIGINT, on_sigint)
  signal.signal(signal.SIGTERM, on_sigint)

  parser = OptionParser()
  parser.add_option('-n', '--host', dest='host', default='54.235.120.254')
  parser.add_option('-p', '--port', dest='port', default='6543')
  parser.add_option('-c', '--concurrency', dest='concurrency', default='1')
  (options, args) = parser.parse_args()

  if len(args) != 2:
    sys.stderr.write('%s [username] [password]\n' % (sys.argv[0]))
    sys.exit(1)

  remote = 'http://%s:%s' % (options.host, options.port)
  print 'Worker version %d connecting to %s' % (WORKER_VERSION, remote)

  worker_info = {
    'uname': platform.uname(),
    'concurrency': options.concurrency,
    'username': args[0],
    'version': WORKER_VERSION,
  }

  global ALIVE
  while ALIVE:
    worker(worker_info, args[1], remote)

if __name__ == '__main__':
  main()
