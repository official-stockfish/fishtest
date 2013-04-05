#!/usr/bin/python
import json
import os
import platform
import signal
import sys
import requests
import time
import traceback
from ConfigParser import SafeConfigParser
from optparse import OptionParser
from games import run_games
from updater import update

WORKER_VERSION = 13
ALIVE = True

def on_sigint(signal, frame):
  global ALIVE
  ALIVE = False

def worker(worker_info, password, remote):
  global ALIVE

  payload = {
    'worker_info': worker_info,
    'password': password,
  }

  try:
    req = requests.post(remote + '/api/request_version', data=json.dumps(payload))
    req = json.loads(req.text)

    if req['version'] > WORKER_VERSION:
      print 'Updating worker version to %d' % (req['version'])
      update()

    req = requests.post(remote + '/api/request_task', data=json.dumps(payload))
    req = json.loads(req.text)
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
    if ALIVE:
      time.sleep(60)
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

  #config file setup
  config_file = 'fishtest.cfg'
  config = SafeConfigParser()
  config.read(config_file)

  parser = OptionParser()
  parser.add_option('-n', '--host', dest='host', default=config.get('parameters','host'))
  parser.add_option('-p', '--port', dest='port', default=config.get('parameters','port'))
  parser.add_option('-c', '--concurrency', dest='concurrency', default=config.get('parameters','concurrency'))
  (options, args) = parser.parse_args()
      
  if len(args) != 2:
    #try to read parameters from the the config file
    username = config.get('login','username')
    password = config.get('login','password')
    if username!='' and password!='':
      args.extend([ username, password ])
    else:
      sys.stderr.write('%s [username] [password]\n' % (sys.argv[0]))
      sys.exit(1)
      
  #write command line parameters to the config file
  config.set('login', 'username', args[0])
  config.set('login', 'password', args[1])
  config.set('parameters', 'host', options.host)
  config.set('parameters', 'port', options.port)
  config.set('parameters', 'concurrency', options.concurrency)
  config.write(open(config_file, 'w')) 

  remote = 'http://%s:%s' % (options.host, options.port)
  print 'Worker version %d connecting to %s' % (WORKER_VERSION, remote)

  worker_info = {
    'uname': platform.uname(),
    'architecture': platform.architecture(),
    'concurrency': options.concurrency,
    'username': args[0],
    'version': WORKER_VERSION,
  }

  global ALIVE
  while ALIVE:
    worker(worker_info, args[1], remote)

if __name__ == '__main__':
  main()
