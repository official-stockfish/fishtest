#!/usr/bin/python
import os
import signal
import subprocess
import time
import zmq
from sys import argv
from rundb import RunDb

CLOP_DIR = os.getenv('CLOP_DIR')

def start_clop(run_id, branch, params):
  rundb = RunDb()
  clopdb = rundb.clopdb

  clopdb.stop_games(run_id)
  time.sleep(1)
  retries = 0
  while clopdb.get_games(run_id).count() > 0 and retries < 5:
    retries += 1
    time.sleep(1)

  this_file = os.path.dirname(os.path.realpath(__file__)) # Points to *.pyc
  this_file = os.path.join(this_file, 'clop_worker', 'clop_worker')
  testName = branch + '_' + run_id
  s = 'Name %s\nScript %s' % (testName, this_file)
  for p in params.split(']'):
    if len(p) == 0:
      continue
    # params is in the form p1[0 100] p2[-10 10]
    name = p.split('[')[0]
    minmax = p.split('[')[1].replace(',', '').split()
    s += '\nIntegerParameter %s %s %s' % (name, minmax[0], minmax[1])
  for i in range(1, 30):
    s += '\nProcessor %s_%d\nProcessor %s_%d' % (run_id, i, run_id, i)
  s += '\nReplications 2\nDrawElo 100\nH 3\nCorrelations all\n'

  print s

  cmd = [os.path.join(CLOP_DIR, 'clop-console'), 'c']
  p = subprocess.Popen(cmd, stdin=subprocess.PIPE, cwd=CLOP_DIR)
  p.stdin.write(s)
  p.stdin.close()

def main():
  rundb = RunDb()

  context = zmq.Context()
  socket = context.socket(zmq.REP)
  socket.bind('tcp://127.0.0.1:5000')
  stream = zmq.ZMQStream(socket)

  from zmq.eventloop import ioloop
  ioloop.install()
  mainloop = ioloop.IOLoop.instance()
  mainloop.start()

  while True:
    for run in rundb.runs.find({'tasks': {'$elemMatch': {'active': True}}}):
      # If is the start of a CLOP tuning session start CLOP.
      if 'clop' in run['args'] and not run['_id'] in active_clop:
        start_clop(str(run['_id']), run['args']['new_tag'], run['args']['clop']['params'])

    if socket.poll(1000) == 0:
      continue
    msg = socket.recv()
    print 'Got:', msg
    socket.send(msg)

  active_clop = []

  data = { 'pid': os.getpid(),
           'run_id': argv[1].split('_')[0],
           'seed': int(argv[2]),
           'params': [(argv[i], argv[i+1]) for i in range(3, len(argv), 2)],
         }

  # Choose the engine's playing side (color) based on CLOP's seed
  data['white'] = True if data['seed'] % 2 == 0 else False

  with open('debug.log', 'a') as f:
    print >>f, data

  # Add new game row in clopdb
  game_id = clopdb.add_game(**data)
  rundb.conn.disconnect() # MongoClient binds a port for listening while connected

  # Go to sleep now, waiting to be wake up when game is done
  signal.pause()

  # Game is finished, read result and remove game row
  game = clopdb.get_game(game_id)
  result = game['result'] if game != None else 'stop'
  clopdb.remove_game(game_id)

  with open('debug.log', 'a') as f:
    print >>f, data, 'result', result

  print result

if __name__ == '__main__':
  main()
