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
from urllib2 import urlopen, HTTPError
from zipfile import ZipFile

FISHCOOKING_URL = 'https://api.github.com/repos/mcostalba/FishCooking'
ARCH = 'ARCH=x86-64' if '64' in platform.architecture()[0] else 'ARCH=x86-32'
EXE_SUFFIX = ''
MAKE_CMD = 'make build COMP=gcc ' + ARCH

if "windows" in platform.system().lower():
  EXE_SUFFIX = '.exe'
  MAKE_CMD = 'mingw32-make build COMP=mingw ' + ARCH

def verify_signature(engine, signature):
  bench_sig = ''
  print 'Verifying signature of %s ...' % (os.path.basename(engine))
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
      print 'Downloading %s ...' % (item)
      blob_json = json.loads(robust_download(blob['url']))
      with open(os.path.join(testing_dir, item), 'wb+') as f:
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

  custom_make = os.path.join(cur_dir, "custom_make.txt")
  if os.path.exists(custom_make):
    with open(custom_make, 'r') as m:
      make_cmd = m.read().strip()
    subprocess.check_call(make_cmd, shell=True)
  else:
    subprocess.check_call(MAKE_CMD + ' -j %s' % (concurrency), shell=True)

  shutil.move('stockfish'+ EXE_SUFFIX, destination)
  os.chdir(cur_dir)
  shutil.rmtree(working_dir)

def run_games(worker_info, password, remote, run, task_id):
  task = run['tasks'][task_id]
  result = {
    'username': worker_info['username'],
    'password': password,
    'run_id': str(run['_id']),
    'task_id': task_id,
    'stats': {'wins':0, 'losses':0, 'draws':0},
  }

  # Have we run any games on this task yet?
  old_stats = task.get('stats', {'wins':0, 'losses':0, 'draws':0})
  games_remaining = task['num_games'] - (old_stats['wins'] + old_stats['losses'] + old_stats['draws'])
  if games_remaining <= 0:
    return 'No games remaining'

  book = run['args'].get('book', 'varied.bin')
  book_depth = run['args'].get('book_depth', '10')

  # Setup testing directory if not already exsisting
  testing_dir = os.path.dirname(os.path.realpath(__file__))
  testing_dir = os.path.join(testing_dir, 'testing')
  if not os.path.exists(testing_dir):
    os.makedirs(testing_dir)

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
    else: zipball = 'cutechess-cli-linux-%s.zip' % (platform.architecture()[0])
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

  p = subprocess.Popen(cmd, stdout=subprocess.PIPE, universal_newlines=True)

  for line in iter(p.stdout.readline,''):
    # Parse line like this:
    # Score of Stockfish  130212 64bit vs base: 1701 - 1715 - 6161  [0.499] 9577
    if 'Score' in line:
      print line
      chunks = line.split(':')
      chunks = chunks[1].split()
      result['stats']['wins']   = int(chunks[0]) + old_stats['wins']
      result['stats']['losses'] = int(chunks[2]) + old_stats['losses']
      result['stats']['draws']  = int(chunks[4]) + old_stats['draws']

      try:
        requests.post(remote + '/api/update_task', data=json.dumps(result))
      except:
        sys.stderr.write('Exception from calling update_task:\n')
        traceback.print_exc(file=sys.stderr)

  p.wait()
  if p.returncode != 0:
    raise Exception('Non-zero return code: %d' % (p.returncode))
