#!/usr/bin/python
import os
import signal
import subprocess
import time
import sys
from rundb import RunDb

def handler(signum, frame):
  return

def test_active():
  ''' Stub, connect to DB'''
  return True

def get_params(run_id):
  ''' Stub, connect to DB '''
  branch = 'test'
  params = [('p1', 0, 10), ('p2', -10, 10), ('p3', -20, 20)]
  return branch, params

def start_clop(clop_dir, run_id):
  branch, params = get_params(run_id)
  this_file = os.path.realpath(__file__)
  testName = branch + '_' + str(run_id)
  s = 'Name %s\nScript %s' % (testName, this_file)
  for p in params:
    s += '\nIntegerParameter %s %d %d' % (p[0], p[1], p[2])
  for i in range(1, 3):
    s += '\nProcessor machine%d\nProcessor machine%d' % (i, i)
  s += '\nReplications 2\nDrawElo 100\nH 3\nCorrelations all\n'

  print s

  os.chdir(clop_dir)
  cmd = [os.path.join(clop_dir, 'clop-console'), 'c']
  p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
  p.stdin.write(s)

def play_game(clopdb, data):
  '''Add new game in clopdb and go to sleep waiting for result'''
  game_id = clopdb.add_game(**data)

  # Go to sleep now, waiting to be wake up when game is done
  signal.pause()

  game = clopdb.get_game(data['pid'])
  result = game.get('result', 'stop')
  clopdb.remove_game(data['pid'])
  return result

def write_result(clopdb, pid, result):
  # TODO Move to fishtest the DB update to avoid a new connection at each result
  '''Update result in clopdb and wake up waiting process'''
  clopdb.write_result(pid, result)
  os.system("kill -14 %d" % (pid))

def main():
  '''Handles CLOP interface in both directions
     We can be called both from fishtest (to start CLOP or
     to update results) and from CLOP (to start a new game)
  '''
  signal.signal(signal.SIGALRM, handler)
  rundb = RunDb()
  clopdb = rundb.clopdb

  if len(sys.argv) < 2:
    sys.exit(1)

  # Start CLOP, called from fishtest
  # arguments are clop_dir and run_id
  if 'start_clop' in sys.argv[1]:
    start_clop(sys.argv[2], sys.argv[3])
    return

  # Result is ready, called from fishtest
  # arguments are process pid and game result
  if 'write_result' in sys.argv[1]:
    write_result(clopdb, int(sys.argv[2]), sys.argv[3])
    return

  # Run a new game, called from CLOP
  # Check if test is still active
  if not test_active():
    print 'stop'
    return

  data = { 'pid': os.getpid(),
           'machine': sys.argv[1],
           'seed': sys.argv[2],
           'params': sys.argv[3:],
         }

  with open('debug.log', 'a') as f:
    print >>f, data

  result = play_game(clopdb, data)

  with open('debug.log', 'a') as f:
    print >>f, data, 'result', result

  print result

if __name__ == '__main__':
  main()
