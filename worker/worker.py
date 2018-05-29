#!/usr/bin/python
from __future__ import print_function

import json
import multiprocessing
import os
import re
import platform
import signal
import sys
import random
import requests
import time
import traceback
import uuid
try:
  from ConfigParser import SafeConfigParser
  config = SafeConfigParser()
except ImportError:
  from configparser import ConfigParser # Python3
  config = ConfigParser()
import zlib
import base64
from optparse import OptionParser
from games import run_games
from updater import update
from datetime import datetime

WORKER_VERSION = 67
ALIVE = True

HTTP_TIMEOUT = 15.0

def setup_config_file(config_file):
  ''' Config file setup, adds defaults if not existing '''
  config.read(config_file)

  mem = 0
  try:
    if 'Linux' in platform.system():
      cmd = 'free'
    else:
      cmd = 'wmic computersystem get TotalPhysicalMemory'
    with os.popen(cmd) as proc:
      mem_str = str(proc.readlines())
    mem = int(re.search(r'\d+', mem_str).group())
    print('Memory: ' + str(mem))
  except:
    traceback.print_exc()
    pass

  defaults = [('login', 'username', ''), ('login', 'password', ''),
              ('parameters', 'host', 'tests.stockfishchess.org'),
              ('parameters', 'port', '80'),
              ('parameters', 'concurrency', '3'),
              ('parameters', 'max_memory', str(int(mem / 2 / 1024))),
              ('parameters', 'min_threads', '1'),
              ]

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
  raise Exception('Terminated by signal')

def worker(worker_info, password, remote):
  global ALIVE

  payload = {
    'worker_info': worker_info,
    'password': password,
  }

  try:
    print('Fetch task...')
    t0 = datetime.utcnow()
    req = requests.post(remote + '/api/request_version', data=json.dumps(payload), headers={'Content-type': 'application/json'}, timeout=HTTP_TIMEOUT)
    req = json.loads(req.text)

    if 'version' not in req:
      print('Incorrect username/password')
      time.sleep(5)
      sys.exit(1)

    if req['version'] > WORKER_VERSION:
      print('Updating worker version to %s' % (req['version']))
      update()
    print("Worker version checked successfully in %ss" % ((datetime.utcnow() - t0).total_seconds()))

    t0 = datetime.utcnow()
    req = requests.post(remote + '/api/request_task', data=json.dumps(payload), headers={'Content-type': 'application/json'}, timeout=HTTP_TIMEOUT)
    req = json.loads(req.text)
  except:
    sys.stderr.write('Exception accessing host:\n')
    traceback.print_exc()
    time.sleep(random.randint(10,60))
    return

  print("Task requested in %ss" % ((datetime.utcnow() - t0).total_seconds()))
  if 'error' in req:
    raise Exception('Error from remote: %s' % (req['error']))

  # No tasks ready for us yet, just wait...
  if 'task_waiting' in req:
    print('No tasks available at this time, waiting...\n')
    # Note that after this sleep we have another ALIVE HTTP_TIMEOUT...
    time.sleep(random.randint(1,10))
    return

  success = True
  run, task_id = req['run'], req['task_id']
  try:
    pgn_file = run_games(worker_info, password, remote, run, task_id)
  except:
    sys.stderr.write('\nException running games:\n')
    traceback.print_exc()
    success = False
  finally:
    payload = {
      'username': worker_info['username'],
      'password': password,
      'run_id': str(run['_id']),
      'task_id': task_id
    }
    try:
      requests.post(remote + '/api/failed_task', data=json.dumps(payload), headers={'Content-type': 'application/json'}, timeout=HTTP_TIMEOUT)
    except:
      pass

    if success and ALIVE:
      sleep = random.randint(1,10)
      print('Wait %d seconds before upload of PGN...' % (sleep))
      time.sleep(sleep)
      if not 'spsa' in run['args']:
        try:
          with open(pgn_file, 'r') as f:
            data = f.read()
          payload['pgn'] = base64.b64encode(zlib.compress(data.encode('utf-8'))).decode()
          print('Uploading compressed PGN of %d bytes' % (len(payload['pgn'])))
          requests.post(remote + '/api/upload_pgn', data=json.dumps(payload), headers={'Content-type': 'application/json'}, timeout=HTTP_TIMEOUT)
        except:
          sys.stderr.write('\nException PGN upload:\n')
          traceback.print_exc()
    try:
      os.remove(pgn_file)
    except:
      pass
    sys.stderr.write('Task exited\n')

  return success

def main():
  print("Worker starting ...\n")
  signal.signal(signal.SIGINT, on_sigint)
  signal.signal(signal.SIGTERM, on_sigint)

  config_file = 'fishtest.cfg'
  config = setup_config_file(config_file)
  parser = OptionParser()
  parser.add_option('-n', '--host', dest='host', default=config.get('parameters', 'host'))
  parser.add_option('-p', '--port', dest='port', default=config.get('parameters', 'port'))
  parser.add_option('-c', '--concurrency', dest='concurrency', default=config.get('parameters', 'concurrency'))
  parser.add_option('-m', '--max_memory', dest='max_memory', default=config.get('parameters', 'max_memory'))
  parser.add_option('-t', '--min_threads', dest='min_threads', default=config.get('parameters', 'min_threads'))
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

  # Re-route old IP
  if '54.235.120.254' in options.host:
    options.host = 'tests.stockfishchess.org'

  # Write command line parameters to the config file
  config.set('login', 'username', args[0])
  config.set('login', 'password', args[1])
  config.set('parameters', 'host', options.host)
  config.set('parameters', 'port', options.port)
  config.set('parameters', 'concurrency', options.concurrency)
  config.set('parameters', 'max_memory', options.max_memory)
  config.set('parameters', 'min_threads', options.min_threads)
  with open(config_file, 'w') as f:
    config.write(f)

  remote = 'http://%s:%s' % (options.host, options.port)
  print('Worker version %s connecting to %s' % (WORKER_VERSION, remote))

  try:
    cpu_count = min(int(options.concurrency), multiprocessing.cpu_count() - 1)
  except:
    cpu_count = int(options.concurrency)

  if cpu_count <= 0:
    sys.stderr.write('Not enough CPUs to run fishtest (it requires at least two)\n')
    sys.exit(1)

  uname = platform.uname()
  worker_info = {
    'uname': uname[0] + ' ' + uname[2],
    'architecture': platform.architecture(),
    'concurrency': cpu_count,
    'max_memory': int(options.max_memory),
    'min_threads': int(options.min_threads),
    'username': args[0],
    'version': "%s:%s" % (WORKER_VERSION, sys.version_info[0]),
    'unique_key': str(uuid.uuid4()),
  }

  success = True
  global ALIVE
  while ALIVE:
    if not success:
      time.sleep(HTTP_TIMEOUT)
    success = worker(worker_info, args[1], remote)

if __name__ == '__main__':
  main()
