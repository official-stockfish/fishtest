from __future__ import absolute_import

import json
import os
import stat
import requests
import subprocess
import shutil
import sys
import tempfile
import time
import traceback
import platform
import zipfile
from base64 import b64decode
from threading import Thread, Event
from urllib2 import urlopen, HTTPError
from zipfile import ZipFile

try:
  from Queue import Queue, Empty
except ImportError:
  from queue import Queue, Empty

FISHCOOKING_URL = 'https://api.github.com/repos/mcostalba/FishCooking'
EXE_SUFFIX = ''
MAKE_CMD = 'make build ARCH=x86-64-modern COMP=gcc'

if "windows" in platform.system().lower():
  EXE_SUFFIX = '.exe'
  MAKE_CMD = 'mingw32-make build ARCH=x86-64-modern COMP=mingw'

def verify_signature(engine, signature):
  bench_sig = ''
  output = subprocess.check_output([engine, 'bench'], stderr=subprocess.STDOUT, universal_newlines=True)
  for line in output.split('\n'):
    if 'Nodes searched' in line:
      bench_sig = line.split(': ')[1].strip()

  if bench_sig != signature:
    raise Exception('Wrong bench in %s Expected: %s Got: %s' % (engine, signature, bench_sig))

def robust_download(url, retries=5):
  """Attempts to download a file for the given number of retries.  If it fails, it will
     throw an exception describing the failure"""
  for retry in xrange(5):
    try:
      response = urlopen(url)
      bytes = response.read()
      if len(bytes) == 0:
        raise Exception('Zero length download %s' % (url))
      return bytes
    except:
      if retry == retries - 1:
        raise
      # Backoff
      time.sleep(1 + retry)

def setup(item, testing_dir):
  """Download item from FishCooking to testing_dir"""
  tree = json.loads(robust_download(FISHCOOKING_URL + '/git/trees/setup'))
  for blob in tree['tree']:
    if blob['path'] == item:
      print 'Downloading %s...' % (item)
      blob_json = json.loads(robust_download(blob['url']))
      with open(os.path.join(testing_dir, item), 'w') as f:
        f.write(b64decode(blob_json['content']))
      break
  else:
    raise Exception('Item %s not found' % (item))

def build(sha, destination, concurrency):
  """Download and build sources in a temporary directory then move exe to destination"""
  cur_dir = os.getcwd()
  working_dir = tempfile.mkdtemp()
  os.chdir(working_dir)

  with open('sf.gz', 'wb+') as f:
    f.write(robust_download(FISHCOOKING_URL + '/zipball/' + sha))
  zip_file = ZipFile('sf.gz')
  zip_file.extractall()
  zip_file.close()

  for name in zip_file.namelist():
    if name.endswith('/src/'):
      src_dir = name
  os.chdir(src_dir)
  subprocess.check_call(MAKE_CMD + ' -j %s' % (concurrency), shell=True)
  shutil.move('stockfish'+ EXE_SUFFIX, destination)
  os.chdir(cur_dir)
  shutil.rmtree(working_dir)

class StoppableThread(Thread):
  def __init__(self):
    super(StoppableThread, self).__init__()
    self._stop = Event()

  def stop(self):
    self._stop.set()

  def stopped(self):
    return self._stop.isSet()

def run_games(testing_dir, worker_info, password, remote, run, task_id):
  task = run['tasks'][task_id]
  result = {
    'username': worker_info['username'],
    'password': password,
    'run_id': str(run['_id']),
    'task_id': task_id,
    'stats': task.get('stats', {'wins':0, 'losses':0, 'draws':0}),
  }

  # Have we run any games on this task yet?
  games_remaining = task['num_games'] - (result['stats']['wins'] + result['stats']['losses'] + result['stats']['draws'])
  if games_remaining <= 0:
    return 'No games remaining'

  book = run['args'].get('book', 'varied.bin')
  book_depth = run['args'].get('book_depth', '10')

  testing_dir = os.path.abspath(testing_dir)
  os.chdir(testing_dir)

  new_engine = os.path.join(testing_dir, 'stockfish' + EXE_SUFFIX)
  base_engine = os.path.join(testing_dir, 'base' + EXE_SUFFIX)
  cutechess = os.path.join(testing_dir, 'cutechess-cli' + EXE_SUFFIX)

  # Download book if not already exsisting
  if not os.path.exists(os.path.join(testing_dir, book)):
    setup(book, testing_dir)

  # Download cutechess if not already exsisting
  if not os.path.exists(cutechess):
    if len(EXE_SUFFIX) > 0: zipball = 'cutechess-cli-win.zip'
    else: zipball = 'cutechess-cli-linux.zip'
    setup(zipball, testing_dir)
    zip_file = ZipFile(zipball)
    zip_file.extractall()
    zip_file.close()
    os.remove(zipball)
    os.chmod(cutechess, os.stat(cutechess).st_mode | stat.S_IEXEC)

  # Download and build base and new
  build(run['args']['resolved_base'], base_engine, worker_info['concurrency'])
  build(run['args']['resolved_new'], new_engine, worker_info['concurrency'])

  if os.path.exists('results.pgn'):
    os.remove('results.pgn')

  # Verify signatures are correct
  if len(run['args']['base_signature']) > 0:
    verify_signature(base_engine, run['args']['base_signature'])

  if len(run['args']['new_signature']) > 0:
    verify_signature(new_engine, run['args']['new_signature'])

  # Run cutechess-cli binary
  cmd = [ cutechess, '-repeat', '-rounds', str(games_remaining), '-resign', 'movecount=3', 'score=400',
          '-draw', 'movenumber=34', 'movecount=2', 'score=20', '-concurrency', worker_info['concurrency'],
          '-engine', 'cmd=stockfish', 'proto=uci', 'option.Threads=1',
          '-engine', 'cmd=base', 'proto=uci', 'option.Threads=1', 'name=base',
          '-each', 'tc=%s' % (run['args']['tc']), 'book=%s' % (book), 'bookdepth=%s' % (book_depth),
          '-tournament', 'gauntlet', '-pgnout', 'results.pgn' ]

  env = dict(os.environ)
  env['LD_LIBRARY_PATH'] = testing_dir
  p = subprocess.Popen(cmd, stderr=sys.stderr, universal_newlines=True, cwd=testing_dir, env=env)

  class EnqueueResults(StoppableThread):
    def __init__(self, queue):
      super(EnqueueResults, self).__init__()
      self.queue = queue

    def run(self):
      while not self.stopped() and not os.path.exists('results.pgn'):
        time.sleep(1)
      pgn = open('results.pgn', 'r')
      while not self.stopped():
        where = pgn.tell()
        line = pgn.readline()
        if not line:
          time.sleep(1)
          pgn.seek(where)
        else:
          self.queue.put(line)
      pgn.close()

  q = Queue()
  t = EnqueueResults(q)
  t.daemon = True
  t.start()

  while True:
    try: line = q.get_nowait()
    except Empty:
      if p.poll() is not None:
        t.stop()
        break
      time.sleep(1)
      continue

    # Parse the PGN for the game result
    if line.startswith('[White'):
      white = line.split('"')[1]
    elif line.startswith('[Black'):
      black = line.split('"')[1]
    elif line.startswith('[Result'):
      game_result = line.split('"')[1]
      if game_result == '1/2-1/2':
        result['stats']['draws'] += 1
      elif game_result == "1-0":
        if black == 'base':
          result['stats']['wins'] += 1
        else:
          result['stats']['losses'] += 1
      elif game_result == "0-1":
        if black == 'base':
          result['stats']['losses'] += 1
        else:
          result['stats']['wins'] += 1
      else:
        sys.stderr.write('Unknown result: %s\n' % (game_result))

      # Post results to server    
      try:
        requests.post(remote + '/api/update_task', data=json.dumps(result))
      except:
        sys.stderr.write('Exception from calling update_task:\n')
        traceback.print_exc(file=sys.stderr)

  if p.returncode != 0:
    raise Exception('Non-zero return code: %d' % (p.returncode))
