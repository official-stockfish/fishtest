#!/usr/bin/python
import platform
import signal
import sys
import requests
import time

DEFAULT_HOST = 'http://54.235.120.254:6543/'
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

def do_work():
  worker_info = get_worker_info()

  global ALIVE
  while ALIVE:
    print 'waiting'
    #r = requests.post(DEFAULT_HOST + 'api/request_task')
    #r.json()

    time.sleep(10)

def main():
  signal.signal(signal.SIGINT, on_sigint)
  do_work()

if __name__ == '__main__':
  main()
