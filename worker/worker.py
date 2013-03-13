#!/usr/bin/python
import json
import os
import platform
import sys
import requests
import time
import traceback
from bson import json_util
from optparse import OptionParser
from games import run_games

def worker_loop(worker_info, password, remote):
  def iter():
    print 'Polling for tasks...'

    payload = {
      'worker_info': worker_info,
      'password': password,
    }
    req = requests.post(remote + '/api/request_task', data=json.dumps(payload))
    req = json.loads(req.text, object_hook=json_util.object_hook)

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
      payload = {
        'username': worker_info['username'],
        'password': password,
        'run_id': str(run['_id']),
        'task_id': task_id
      }
      requests.post(remote + '/api/failed_task', data=json.dumps(payload))
      sys.stderr.write('\nDisconnected from host\n')
      raise

  # Run tasks until we hit five consecutive failures
  failed = 0
  while failed < 5:
    try:
      iter()
      failed = 0
    except:
      failed += 1
      traceback.print_exc()
      time.sleep(10)

def main():
  parser = OptionParser()
  parser.add_option('-n', '--host', dest='host', default='54.235.120.254')
  parser.add_option('-p', '--port', dest='port', default='6543')
  parser.add_option('-c', '--concurrency', dest='concurrency', default='1')
  (options, args) = parser.parse_args()

  if len(args) != 2:
    sys.stderr.write('%s [username] [password]\n' % (sys.argv[0]))
    sys.exit(1)

  remote = 'http://%s:%s' % (options.host, options.port)
  print 'Launching with %s' % (remote)

  worker_info = {
    'uname' : platform.uname(),
    'concurrency' : options.concurrency,
    'username' : args[0],
  }

  worker_loop(worker_info, args[1], remote)

if __name__ == '__main__':
  main()
