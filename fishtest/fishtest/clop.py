#!/usr/bin/python
import os
import signal
import subprocess
import threading
import time
import zmq
from bson.objectid import ObjectId
from sys import argv
from rundb import RunDb
from zmq.eventloop import ioloop, zmqstream

CLOP_DIR = os.getenv('CLOP_DIR')

def read_clop_status(p, rundb, run_id):
  for line in iter(p.stdout.readline, ''):
    rundb.runs.update({'_id': ObjectId(run_id)}, {'$set': {'args.clop.status': line}})
  
def start_clop(rundb, clopdb, run_id, branch, params):
  this_file = os.path.dirname(os.path.realpath(__file__)) # Points to *.pyc
  this_file = os.path.join(this_file, 'clop_worker', 'clop_worker')
  test_name = branch + '_' + run_id
  s = 'Name %s\nScript %s' % (test_name, this_file)
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

  print 'Starting task', run_id

  cmd = [os.path.join(CLOP_DIR, 'clop-console'), 'c']
  clop_output = open(os.path.join(CLOP_DIR, test_name), 'w')
  p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, cwd=CLOP_DIR)
  p.stdin.write(s)
  p.stdin.close()

  # Start a thread to read the output from the clop-console process
  status_thread = threading.Thread(target=read_clop_status, args=(p, rundb, run_id))
  status_thread.start()

  return {
    'thread': status_thread,
    'process': p,
  }

GAME_ID_TO_STREAM = {}

def main():
  rundb = RunDb()
  clopdb = rundb.clopdb

  def on_clop_request(stream, message):
    client_id = message[0]
    message = message[2:]
    data = {
      'run_id': message[0].split('_')[0],
      'seed': int(message[1]),
      'params': [(message[i], message[i+1]) for i in range(2, len(message), 2)],
    }

    # Choose the engine's playing side (color) based on CLOP's seed
    data['white'] = True if data['seed'] % 2 == 0 else False

    # Add new game row in clopdb
    game_id = str(clopdb.add_game(**data))
    GAME_ID_TO_STREAM[game_id] = (stream, client_id)

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

    if game_id in GAME_ID_TO_STREAM:
      stream, client_id = GAME_ID_TO_STREAM[game_id]
      stream.send(client_id, zmq.SNDMORE)
      stream.send('', zmq.SNDMORE)
      stream.send_unicode(result)
    else:
      print 'Missing game_id!'

  context = zmq.Context()

  client_socket = context.socket(zmq.ROUTER)
  client_socket.bind('tcp://127.0.0.1:5000')
  client_stream = zmqstream.ZMQStream(client_socket)
  client_stream.on_recv_stream(on_clop_request)

  server_socket = context.socket(zmq.SUB)
  server_socket.connect('tcp://127.0.0.1:5001')
  server_socket.setsockopt(zmq.SUBSCRIBE, '')
  server_stream = zmqstream.ZMQStream(server_socket)
  server_stream.on_recv(on_game_finished)

  active_clop = dict()
  def check_runs():
    # Check if the clop runs are still active
    for run_id, info in active_clop.items():
      run = rundb.get_run(run_id)
      alive = False
      for task in run['tasks']:
        if task['active']:
          alive = True
      if not alive:
        print 'Killing task', run_id
        for game in clopdb.get_games(run_id):
          on_game_finished(game['_id'])

        info['process'].kill()
        del active_clop[run_id]

    for run in rundb.runs.find({'tasks': {'$elemMatch': {'active': True}}}):
      # If is the start of a CLOP tuning session start CLOP.
      if 'clop' in run['args'] and run['_id'] not in active_clop:
        active_clop[run['_id']] = start_clop(rundb, clopdb, str(run['_id']), run['args']['new_tag'], run['args']['clop']['params'])


  check_runs_timer = ioloop.PeriodicCallback(check_runs, 20 * 1000)
  check_runs_timer.start()

  ioloop.install()
  mainloop = ioloop.IOLoop.instance()
  mainloop.start()

if __name__ == '__main__':
  main()
