#!/usr/bin/python
import platform
import signal
import sys
import requests
import time

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

def request_task(remote, worker_info):
  r = requests.post(remote + '/api/request_task')
  r.json()

def worker_loop(remote):
  worker_info = get_worker_info()

  global ALIVE
  while ALIVE:
    print 'polling for tasks...'
    try:
      request_task(remote, worker_info)
    except:
      sys.stderr.write('Exception from worker:\n')
      traceback.print_exc(file=sys.stderr)

    time.sleep(10)

def main():
  parser = OptionParser()
  parser.add_option('-h', '--host', dest='host', default='54.235.120.254')
  parser.add_option('-p', '--port', dest='port', default='6543')
  (options, args) = parser.parse_args()

  remote = 'http://%s:%s' % (options.host, options.port) 
  print 'Launching with %s' % (remote)

  signal.signal(signal.SIGINT, on_sigint)
  worker_loop(remote)

if __name__ == '__main__':
  main()
