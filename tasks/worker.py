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

ALIVE = True

def on_sigint(signal, frame):
  global ALIVE
  if ALIVE:
    sys.stderr.write('Shutting down gracefully...\n')
    ALIVE = False
    return

  sys.stderr.write('Hard shutdown!  Tasks may be incomplete\n')
  sys.exit(0)


def worker_loop(testing_dir, worker_info, password, remote):
  global ALIVE
  while ALIVE:
    print 'Polling for tasks...'
    try:
      payload = {
        'worker_info': worker_info,
        'password': password,
      }
      req = requests.post(remote + '/api/request_task', data=json.dumps(payload))
      req = json.loads(req.text, object_hook=json_util.object_hook)

      if 'error' in req:
        raise Exception('Error from remote: %s' % (req['error']))

      if 'task_waiting' not in req:
        (run, task_id) = { req['run'], req['task_id'] }
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
          raise

    except:
      sys.stderr.write('Exception from worker:\n')
      traceback.print_exc(file=sys.stderr)

    time.sleep(10)


def main():

  signal.signal(signal.SIGINT, on_sigint)
  signal.signal(signal.SIGTERM, on_sigint)

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
