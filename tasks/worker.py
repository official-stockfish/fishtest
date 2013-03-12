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

def worker_loop(testing_dir, worker_info, password, remote):
  while True:
    print 'Polling for tasks...'

    payload = {
      'worker_info': worker_info,
      'password': password,
    }
    try:
      req = requests.post(remote + '/api/request_task', data=json.dumps(payload))
      req = json.loads(req.text, object_hook=json_util.object_hook)
    except:
      sys.stderr.write('Exception accessing request_task:\n')
      raise

    if 'error' in req:
      raise Exception('Error from remote: %s' % (req['error']))

    if 'task_waiting' not in req:
      run, task_id = req['run'], req['task_id']
      try:
        run_games(testing_dir, worker_info, password, remote, run, task_id)
      except:
        payload = {
          'username': worker_info['username'],
          'password': password,
          'run_id': str(run['_id']),
          'task_id': task_id
        }
        requests.post(remote + '/api/failed_task', data=json.dumps(payload))
        sys.stderr.write('Disconnected from host')
        raise

    time.sleep(10)

def main():
  parser = OptionParser()
  parser.add_option('-n', '--host', dest='host', default='54.235.120.254')
  parser.add_option('-p', '--port', dest='port', default='6543')
  parser.add_option('-c', '--concurrency', dest='concurrency', default='1')
  (options, args) = parser.parse_args()

  if len(args) != 3:
    sys.stderr.write('%s [username] [password] [testing_dir]\n' % (sys.argv[0]))
    sys.exit(1)

  testing_dir = args[2]
  if not os.path.exists(testing_dir):
    raise Exception('Testing directory does not exist: %s' % (testing_dir))

  remote = 'http://%s:%s' % (options.host, options.port)
  print 'Launching with %s' % (remote)

  worker_info = {
    'uname' : platform.uname(),
    'concurrency' : options.concurrency,
    'username' : args[0],
  }

  worker_loop(testing_dir, worker_info, args[1], remote)

if __name__ == '__main__':
  main()
