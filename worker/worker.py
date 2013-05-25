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

WORKER_VERSION = 29
ALIVE = True

def setup_config_file(config_file):
  ''' Config file setup, adds defaults if not exsisting '''
  config = SafeConfigParser()
  config.read(config_file)

  defaults = [('login', 'username', ''), ('login', 'password', ''),
              ('parameters', 'host', '54.235.120.254'),
              ('parameters', 'port', '80'),
              ('parameters', 'concurrency', '3')]

  for v in defaults:
    if not config.has_section(v[0]):
      config.add_section(v[0])
    if not config.has_option(v[0], v[1]):
      config.set(*v)
      with open(config_file, 'w') as f:
        config.write(f)

  return config

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
      time.sleep(300)
  finally:
    payload = {
      'username': worker_info['username'],
      'password': password,
      'run_id': str(run['_id']),
      'task_id': task_id
    }
    try:
      requests.post(remote + '/api/failed_task', data=json.dumps(payload))
    except:
      pass
    sys.stderr.write('Task exited\n')

def main():
  signal.signal(signal.SIGINT, on_sigint)
  signal.signal(signal.SIGTERM, on_sigint)

  config_file = 'fishtest.cfg'
  config = setup_config_file(config_file)
  parser = OptionParser()
  parser.add_option('-n', '--host', dest='host', default=config.get('parameters', 'host'))
  parser.add_option('-p', '--port', dest='port', default=config.get('parameters', 'port'))
  parser.add_option('-c', '--concurrency', dest='concurrency', default=config.get('parameters', 'concurrency'))
  (options, args) = parser.parse_args()

  if len(args) != 2:
    # Try to read parameters from the the config file
    username = config.get('login', 'username')
    password = config.get('login', 'password', raw=True)
    if len(username) != 0 and len(password) != 0:
      args.extend([ username, password ])
    else:
      sys.stderr.write('%s [username] [password]\n' % (sys.argv[0]))
      sys.exit(1)

  # Write command line parameters to the config file
  config.set('login', 'username', args[0])
  config.set('login', 'password', args[1])
  config.set('parameters', 'host', options.host)
  config.set('parameters', 'port', options.port)
  config.set('parameters', 'concurrency', options.concurrency)
  with open(config_file, 'w') as f:
    config.write(f)

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
