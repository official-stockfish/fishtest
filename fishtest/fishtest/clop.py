#!/usr/bin/python
import os
import signal
import subprocess
import time
from sys import argv
from rundb import RunDb

CLOP_DIR = './clop/'

def handler(signum, frame):
  return

def test_active():
  ''' Stub, connect to DB'''
  return True

def start_clop(run_id, branch, params):
  this_file = os.path.dirname(os.path.realpath(__file__)) # Points to *.pyc
  this_file = os.path.join(this_file, 'clop.py')
  testName = branch + '_' + run_id
  s = 'Name %s\nScript %s' % (testName, this_file)
  for p in params.split(']'):
    if len(p) == 0:
      continue
    # params is in the form p1[0 100] p2[-10 10]
    name = p.split('[')[0]
    minmax = p.split('[')[1].split()
    s += '\nIntegerParameter %s %s %s' % (name, minmax[0], minmax[1])
  for i in range(1, 3):
    s += '\nProcessor machine%d\nProcessor machine%d' % (i, i)
  s += '\nReplications 2\nDrawElo 100\nH 3\nCorrelations all\n'

  print s

  cmd = [os.path.join(CLOP_DIR, 'clop-console'), 'c']
  p = subprocess.Popen(cmd, stdin=subprocess.PIPE, cwd=CLOP_DIR)
  p.stdin.write(s)
  p.stdin.close()

def main():
  '''Called by CLOP to start a new game'''
  signal.signal(signal.SIGALRM, handler)
  rundb = RunDb()
  clopdb = rundb.clopdb

  # Run a new game, called from CLOP
  # Check if test is still active
  if not test_active():
    print 'stop'
    return

  data = { 'pid': os.getpid(),
           'machine': argv[1],
           'seed': int(argv[2]),
           'params': [(argv[i], argv[i+1]) for i in range(3, len(argv), 2)],
         }

  # Choose the engine's playing side (color) based on CLOP's seed
  data['white'] = True if data['seed'] % 2 == 0 else False

  with open('debug.log', 'a') as f:
    print >>f, data

  # Add new game row in clopdb
  game_id = clopdb.add_game(**data)

  # Go to sleep now, waiting to be wake up when game is done
  signal.pause()

  # Game is finished, read result and remove game row
  game = clopdb.get_game(game_id)
  result = game.get('result', 'stop')
  clopdb.remove_game(game_id)

  with open('debug.log', 'a') as f:
    print >>f, data, 'result', result

  print result

if __name__ == '__main__':
  main()
