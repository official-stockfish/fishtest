#!/usr/bin/python
import os
import signal
import subprocess
import time
import zmq
from sys import argv
from rundb import RunDb
from zmq.eventloop import ioloop, zmqstream

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

GAME_ID_TO_STREAM = {}

def on_clop_request(stream, message):
  data = { 'pid': int(message[0]),
           'run_id': message[1].split('_')[0],
           'seed': int(message[2]),
           'params': [(message[i], message[i+1]) for i in range(3, len(message), 2)],
         }

  # Choose the engine's playing side (color) based on CLOP's seed
  data['white'] = True if data['seed'] % 2 == 0 else False

  # Add new game row in clopdb
  game_id = clopdb.add_game(**data)
  GAME_ID_TO_STREAM[game_id] = stream

  with open('debug.log', 'a') as f:
    print >>f, game_id, data

def on_game_finished(message):
  # Game is finished, read result and remove game row
  game_id = message[0]
  game = clopdb.get_game(game_id)
  result = game['result'] if game != None else 'stop'
  clopdb.remove_game(game_id)

  with open('debug.log', 'a') as f:
    print >>f, game_id, 'result', result

  GAME_ID_TO_STREAM[game_id].send(result)

def main():
  rundb = RunDb()

  context = zmq.Context()

  client_socket = context.socket(zmq.REP)
  client_socket.bind('tcp://127.0.0.1:5000')
  client_stream = zmqstream.ZMQStream(client_socket)
  client_stream.on_recv_stream(on_clop_request)

  server_socket = context.socket(zmq.SUB)
  server_socket.connect('tcp://127.0.0.1:5001')
  server_socket.setsockopt(zmq.SUBSCRIBE, '')
  server_stream = zmqstream.ZMQStream(server_socket)
  server_stream.on_recv(on_game_finished)

  active_clop = set()
  def check_runs():
    for run in rundb.runs.find({'tasks': {'$elemMatch': {'active': True}}}):
      # If is the start of a CLOP tuning session start CLOP.
      if 'clop' in run['args'] and run['_id'] not in active_clop:
        active_clop.add(run['_id'])
        start_clop(str(run['_id']), run['args']['new_tag'], run['args']['clop']['params'])

  check_runs_timer = ioloop.PeriodicCallback(check_runs, 30 * 1000)
  check_runs_timer.start()

  ioloop.install()
  mainloop = ioloop.IOLoop.instance()
  mainloop.start()

if __name__ == '__main__':
  main()
