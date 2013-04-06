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
from zipfile import ZipFile

FISHCOOKING_URL = 'https://api.github.com/repos/mcostalba/FishCooking'
ARCH = 'ARCH=x86-64-modern' if '64' in platform.architecture()[0] else 'ARCH=x86-32'
EXE_SUFFIX = ''
MAKE_CMD = 'make build COMP=gcc ' + ARCH

IS_WINDOWS = 'windows' in platform.system().lower()
if IS_WINDOWS:
  EXE_SUFFIX = '.exe'
  MAKE_CMD = 'mingw32-make build COMP=mingw ' + ARCH

def verify_signature(engine, signature, remote, payload):
  bench_sig = ''
  print 'Verifying signature of %s ...' % (os.path.basename(engine))
  with open(os.devnull, 'wb') as f:
    p = subprocess.Popen([engine, 'bench'], stderr=subprocess.PIPE, stdout=f, universal_newlines=True)
  for line in iter(p.stderr.readline,''):
    if 'Nodes searched' in line:
      bench_sig = line.split(': ')[1].strip()
    if 'Nodes/second' in line:
      bench_nps = float(line.split(': ')[1].strip())

  p.wait()
  if p.returncode != 0:
    raise Exception('Bench exited with non-zero code %d' % (p.returncode))

  if int(bench_sig) != int(signature):
    requests.post(remote + '/api/stop_run', data=json.dumps(payload))
    raise Exception('Wrong bench in %s Expected: %s Got: %s' % (engine, signature, bench_sig))

  return bench_nps

def setup(item, testing_dir):
  """Download item from FishCooking to testing_dir"""
  tree = requests.get(FISHCOOKING_URL + '/git/trees/setup').json()
  for blob in tree['tree']:
    if blob['path'] == item:
      print 'Downloading %s ...' % (item)
      blob_json = requests.get(blob['url']).json()
      with open(os.path.join(testing_dir, item), 'wb+') as f:
        f.write(b64decode(blob_json['content']))
      break
  else:
    raise Exception('Item %s not found' % (item))

def build(worker_dir, sha, destination, concurrency):
  """Download and build sources in a temporary directory then move exe to destination"""
  tmp_dir = tempfile.mkdtemp()
  os.chdir(tmp_dir)

  with open('sf.gz', 'wb+') as f:
    f.write(requests.get(FISHCOOKING_URL + '/zipball/' + sha).content)
  zip_file = ZipFile('sf.gz')
  zip_file.extractall()
  zip_file.close()

  for name in zip_file.namelist():
    if name.endswith('/src/'):
      src_dir = name
  os.chdir(src_dir)

  custom_make = os.path.join(worker_dir, 'custom_make.txt')
  if os.path.exists(custom_make):
    with open(custom_make, 'r') as m:
      make_cmd = m.read().strip()
    subprocess.check_call(make_cmd, shell=True)
  else:
    subprocess.check_call(MAKE_CMD + ' -j %s' % (concurrency), shell=True)

  shutil.move('stockfish'+ EXE_SUFFIX, destination)
  os.chdir(worker_dir)
  shutil.rmtree(tmp_dir)

def setup_engine(destination, url, worker_dir, sha, concurrency):
  if os.path.exists(destination): os.remove(destination)
  if len(url) > 0:
    with open(destination, 'wb+') as f:
      f.write(requests.get(url).content)
  else:
    build(worker_dir, sha, destination, concurrency)

def kill_process(p):
  if IS_WINDOWS:
    # Kill doesn't kill subprocesses on Windows
    subprocess.call(['taskkill', '/F', '/T', '/PID', str(p.pid)])
  else:
    p.kill()

def adjust_tc(tc, base_nps):
  factor = 1500000.0 / base_nps # Set target NPS to 1500000

  # Parse the time control in cutechess format
  chunks = tc.split('+')
  increment = 0.0
  if len(chunks) == 2:
    increment = float(chunks[1])

  chunks = chunks[0].split('/')
  num_moves = 0
  if len(chunks) == 2:
    num_moves = int(chunks[0])

  time_tc = chunks[-1]
  chunks = time_tc.split(':')
  if len(chunks) == 2:
    time_tc = float(chunks[0]) * 60 + float(chunks[1])
  else:
    time_tc = float(chunks[0])

  # Rebuild scaled_tc now
  scaled_tc = '%.2f' % (time_tc * factor)
  if increment > 0.0:
    scaled_tc += '+%.2f' % (increment)
  if num_moves > 0:
    scaled_tc = '%d/%s' % (num_moves, scaled_tc)

  print 'CPU factor : %f - tc adjusted to %s' % (factor, scaled_tc)
  return scaled_tc

def run_games(worker_info, password, remote, run, task_id):
  task = run['tasks'][task_id]
  result = {
    'username': worker_info['username'],
    'password': password,
    'run_id': str(run['_id']),
    'task_id': task_id,
    'stats': {'wins':0, 'losses':0, 'draws':0, 'crashes':0},
  }

  # Have we run any games on this task yet?
  old_stats = task.get('stats', {'wins':0, 'losses':0, 'draws':0, 'crashes':0})
  result['stats']['crashes'] = old_stats.get('crashes', 0)
  games_remaining = task['num_games'] - (old_stats['wins'] + old_stats['losses'] + old_stats['draws'])
  if games_remaining <= 0:
    raise Exception('No games remaining')

  book = run['args'].get('book', 'varied.bin')
  book_depth = run['args'].get('book_depth', '10')
  new_options = run['args'].get('new_options', 'Hash=128 OwnBook=false')
  base_options = run['args'].get('base_options', 'Hash=128 OwnBook=false')
  threads = int(run['args'].get('threads', 1))
  new_url = run.get('new_engine_url', '')
  base_url = run.get('base_engine_url', '')
  games_concurrency = int(worker_info['concurrency']) / threads

  # Format options according to cutechess syntax
  new_options = ['option.'+x for x in new_options.split()]
  base_options = ['option.'+x for x in base_options.split()]

  # Setup testing directory if not already exsisting
  worker_dir = os.path.dirname(os.path.realpath(__file__))
  testing_dir = os.path.join(worker_dir, 'testing')
  if not os.path.exists(testing_dir):
    os.makedirs(testing_dir)

  new_engine = os.path.join(testing_dir, 'stockfish' + EXE_SUFFIX)
  base_engine = os.path.join(testing_dir, 'base' + EXE_SUFFIX)
  cutechess = os.path.join(testing_dir, 'cutechess-cli' + EXE_SUFFIX)

  # We have already run another task from the same run ?
  run_id_file = os.path.join(testing_dir, 'run_id.txt')
  if os.path.exists(run_id_file):
    with open(run_id_file, 'r') as f:
      run_id = f.read().strip()
  else:
      run_id = ''

  # Download or build from sources base and new
  if str(run['_id']) != run_id:
    if os.path.exists(run_id_file): os.remove(run_id_file)
    setup_engine(new_engine, new_url, worker_dir, run['args']['resolved_new'], worker_info['concurrency'])
    setup_engine(base_engine, base_url, worker_dir, run['args']['resolved_base'], worker_info['concurrency'])
    with open(run_id_file, 'w') as f:
      f.write(str(run['_id']))

  os.chdir(testing_dir)

  # Download book if not already existing
  if not os.path.exists(os.path.join(testing_dir, book)):
    setup(book, testing_dir)

  # Download cutechess if not already existing
  if not os.path.exists(cutechess):
    if len(EXE_SUFFIX) > 0: zipball = 'cutechess-cli-win.zip'
    else: zipball = 'cutechess-cli-linux-%s.zip' % (platform.architecture()[0])
    setup(zipball, testing_dir)
    zip_file = ZipFile(zipball)
    zip_file.extractall()
    zip_file.close()
    os.remove(zipball)
    os.chmod(cutechess, os.stat(cutechess).st_mode | stat.S_IEXEC)

  if os.path.exists('results.pgn'):
    os.remove('results.pgn')

  # Verify signatures are correct
  if len(run['args']['base_signature']) > 0:
    base_nps = verify_signature(base_engine, run['args']['base_signature'], remote, result)

  if len(run['args']['new_signature']) > 0:
    verify_signature(new_engine, run['args']['new_signature'], remote, result)

  # Benchmark to adjust cpu scaling
  scaled_tc = adjust_tc(run['args']['tc'], base_nps)

  # Run cutechess-cli binary
  cmd = [ cutechess, '-repeat', '-rounds', str(games_remaining), '-tournament',
         'gauntlet', '-pgnout', 'results.pgn', '-resign', 'movecount=3', 'score=400',
         '-draw', 'movenumber=34', 'movecount=2', 'score=20', '-concurrency',
         str(games_concurrency), '-engine', 'name=stockfish', 'cmd=stockfish'] + new_options + [
         '-engine', 'name=base', 'cmd=base'] + base_options + ['-each', 'proto=uci',
         'option.Threads=%d' % (threads), 'tc=%s' % (scaled_tc),
         'book=%s' % (book), 'bookdepth=%s' % (book_depth) ]

  print 'Running %s vs %s' % (run['args']['new_tag'], run['args']['base_tag'])
  print ' '.join(cmd)
  p = subprocess.Popen(cmd, stdout=subprocess.PIPE, universal_newlines=True)

  try:
    for line in iter(p.stdout.readline,''):
      sys.stdout.write(line)
      sys.stdout.flush()
      # Parse line like this:
      # Finished game 1 (stockfish vs base): 0-1 {White disconnects}
      if 'disconnects' in line or 'connection stalls' in line:
        result['stats']['crashes'] += 1

      # Parse line like this:
      # Score of stockfish vs base: 0 - 0 - 1  [0.500] 1
      if 'Score' in line:
        chunks = line.split(':')
        chunks = chunks[1].split()
        result['stats']['wins']   = int(chunks[0]) + old_stats['wins']
        result['stats']['losses'] = int(chunks[2]) + old_stats['losses']
        result['stats']['draws']  = int(chunks[4]) + old_stats['draws']

        try:
          status = requests.post(remote + '/api/update_task', data=json.dumps(result)).json()
          if not status['task_alive']:
            # This task is no longer neccesary
            kill_process(p)
            p.wait()
            return
        except:
          sys.stderr.write('Exception from calling update_task:\n')
          traceback.print_exc(file=sys.stderr)
  except:
    kill_process(p)

  p.wait()
  if p.returncode != 0:
    raise Exception('Non-zero return code: %d' % (p.returncode))
