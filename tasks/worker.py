#!/usr/bin/python
import json
import platform
import signal
import sys
import requests
import time
import traceback
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

def get_worker_info():
  return {
    'uname': platform.uname(),
  }

def request_task(worker_info, remote):
  r = requests.post(remote + '/api/request_task', data=json.dumps({'worker_info': worker_info}))
  task = json.loads(r.json())

  run_games(worker_info, remote, task['run'], task['task_id'])

def worker_loop(worker_info, remote):
  global ALIVE
  while ALIVE:
    print 'polling for tasks...'
    try:
      request_task(worker_info, remote)
    except:
      sys.stderr.write('Exception from worker:\n')
      traceback.print_exc(file=sys.stderr)

    time.sleep(10)

def main():
  parser = OptionParser()
  parser.add_option('-n', '--host', dest='host', default='54.235.120.254')
  parser.add_option('-p', '--port', dest='port', default='6543')
  parser.add_option('-c', '--concurrency', dest='concurrency', default='1')
  (options, args) = parser.parse_args()

  remote = 'http://%s:%s' % (options.host, options.port)
  print 'Launching with %s' % (remote)

  worker_info = get_worker_info()
  worker_info['concurrency'] = options.concurrency

  signal.signal(signal.SIGINT, on_sigint)
  worker_loop(worker_info, remote)

if __name__ == '__main__':
  main()
