from __future__ import absolute_import

import datetime
import json
import os
import stat
import requests
import subprocess
import shutil
import sys
import tempfile
import threading
import time
import traceback
import platform
import zipfile
from base64 import b64decode
from zipfile import ZipFile

try:
  from Queue import Queue, Empty
except ImportError:
  from queue import Queue, Empty  # python 3.x

# Global beacuse is shared across threads
old_stats = {'wins':0, 'losses':0, 'draws':0, 'crashes':0, 'time_losses':0}

IS_WINDOWS = 'windows' in platform.system().lower()

def is_windows_64bit():
  if 'PROCESSOR_ARCHITEW6432' in os.environ:
    return True
  return os.environ['PROCESSOR_ARCHITECTURE'].endswith('64')

def is_64bit():
  if IS_WINDOWS:
    return is_windows_64bit()
  return '64' in platform.architecture()[0]

FISHCOOKING_URL = 'https://github.com/mcostalba/FishCooking'
ARCH = 'ARCH=x86-64-modern' if is_64bit() else 'ARCH=x86-32'
EXE_SUFFIX = ''
MAKE_CMD = 'make build COMP=gcc ' + ARCH

if IS_WINDOWS:
  EXE_SUFFIX = '.exe'
  MAKE_CMD = 'mingw32-make build COMP=mingw ' + ARCH

def binary_filename(sha):
  system = platform.uname()[0].lower()
  architecture = '64' if is_64bit() else '32'
  return sha + '_' + system + '_' + architecture

def get_clop_result(wld, white):
  ''' Convert result to W or L or D'''
  if wld[0] == 1:
    return 'W' if white else 'L'
  elif wld[1] == 1:
    return 'L' if white else 'W'
  else:
    return 'D'

def github_api(repo):
  """ Convert from https://github.com/<user>/<repo>
      To https://api.github.com/repos/<user>/<repo> """
  return repo.replace('https://github.com', 'https://api.github.com/repos')

def verify_signature(engine, signature, remote, payload, concurrency):
  if concurrency > 1:
    busy_process = subprocess.Popen([engine], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    busy_process.stdin.write('setoption name Threads value %d\n' % (concurrency-1))
    busy_process.stdin.write('go infinite\n')

  try:
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
      message = 'Wrong bench in %s Expected: %s Got: %s' % (engine, signature, bench_sig)
      payload['message'] = message
      requests.post(remote + '/api/stop_run', data=json.dumps(payload))
      raise Exception(message)

  finally:
    if concurrency > 1:
      busy_process.stdin.write('quit\n')
      busy_process.kill()

  return bench_nps

def setup(item, testing_dir):
  """Download item from FishCooking to testing_dir"""
  tree = requests.get(github_api(FISHCOOKING_URL) + '/git/trees/setup').json()
  for blob in tree['tree']:
    if blob['path'] == item:
      print 'Downloading %s ...' % (item)
      blob_json = requests.get(blob['url']).json()
      with open(os.path.join(testing_dir, item), 'wb+') as f:
        f.write(b64decode(blob_json['content']))
      break
  else:
    raise Exception('Item %s not found' % (item))

def build(worker_dir, sha, repo_url, destination, concurrency):
  """Download and build sources in a temporary directory then move exe to destination"""
  tmp_dir = tempfile.mkdtemp()
  os.chdir(tmp_dir)

  with open('sf.gz', 'wb+') as f:
    f.write(requests.get(github_api(repo_url) + '/zipball/' + sha).content)
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

def setup_engine(destination, binaries_url, worker_dir, sha, repo_url, concurrency):
  if os.path.exists(destination): os.remove(destination)
  if len(binaries_url) > 0:
    try:
      binary_url = binaries_url + '/' + binary_filename(sha)
      r = requests.get(binary_url)
      if r.status_code == 200:
        print 'Downloaded %s from %s' % (os.path.basename(destination), binary_url)
        with open(destination, 'wb+') as f:
          f.write(r.content)
        return
    except:
      sys.stderr.write('Unable to download exe, fall back on local compile:\n')
      traceback.print_exc(file=sys.stderr)

  build(worker_dir, sha, repo_url, destination, concurrency)

def kill_process(p):
  if IS_WINDOWS:
    # Kill doesn't kill subprocesses on Windows
    subprocess.call(['taskkill', '/F', '/T', '/PID', str(p.pid)])
  else:
    p.kill()

def adjust_tc(tc, base_nps, concurrency):
  factor = 1600000.0 / base_nps
  if base_nps < 700000:
    sys.stderr.write('This machine is too slow to run fishtest effectively - sorry!\n')
    sys.exit(1)

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
  tc_limit = time_tc * factor * 3
  if increment > 0.0:
    scaled_tc += '+%.2f' % (increment)
    tc_limit += increment * 200
  if num_moves > 0:
    scaled_tc = '%d/%s' % (num_moves, scaled_tc)
    tc_limit *= 100.0 / num_moves

  print 'CPU factor : %f - tc adjusted to %s' % (factor, scaled_tc)
  return scaled_tc, tc_limit

def enqueue_output(out, queue):
  for line in iter(out.readline, b''):
    queue.put(line)
  out.close()

def run_game(p, remote, result, clop, clop_tuning, tc_limit):
  global old_stats
  failed_updates = 0

  q = Queue()
  t = threading.Thread(target=enqueue_output, args=(p.stdout, q))
  t.daemon = True
  t.start()

  end_time = datetime.datetime.now() + datetime.timedelta(seconds=tc_limit)
  while datetime.datetime.now() < end_time:
    try: line = q.get_nowait()
    except Empty:
      if p.poll() != None:
        break
      time.sleep(1)
      continue

    sys.stdout.write(line)
    sys.stdout.flush()

    # Cutechess can exit unexpectedly
    if 'Finished match' in line:
      kill_process(p)
      break

    # Parse line like this:
    # Finished game 1 (stockfish vs base): 0-1 {White disconnects}
    if 'disconnects' in line or 'connection stalls' in line:
      result['stats']['crashes'] += 1

    if 'on time' in line:
      result['stats']['time_losses'] += 1

    # Parse line like this:
    # Score of stockfish vs base: 0 - 0 - 1  [0.500] 1
    if 'Score' in line:
      chunks = line.split(':')
      chunks = chunks[1].split()
      wld = [int(chunks[0]), int(chunks[2]), int(chunks[4])]
      result['stats']['wins']   = wld[0] + old_stats['wins']
      result['stats']['losses'] = wld[1] + old_stats['losses']
      result['stats']['draws']  = wld[2] + old_stats['draws']

      if clop_tuning:
        clop['game_result'] = get_clop_result(wld, clop['white'])
        old_stats = result['stats'] # FIXME player color is not correctly handled
        result['clop'] = clop

      try:
        req = requests.post(remote + '/api/update_task', data=json.dumps(result)).json()
        failed_updates = 0

        if not req['task_alive']:
          # This task is no longer neccesary
          kill_process(p)
          return req

      except:
        sys.stderr.write('Exception from calling update_task:\n')
        traceback.print_exc(file=sys.stderr)
        failed_updates += 1
        if failed_updates > 5:
          kill_process(p)
          break

  if datetime.datetime.now() >= end_time:
    kill_process(p)

  return { 'task_alive': True }

def launch_cutechess(cmd, remote, result, clop_tuning, regression_test, tc_limit):
  clop = {
    'fcp': [],
    'scp': [],
  }

  if clop_tuning:
    # Request parameters for next game
    req = requests.post(remote + '/api/request_clop', data=json.dumps(result)).json()

    if 'game_id' in req:
      clop['game_id'] = req['game_id']
      clop['white'] = req['white']
      clop['fcp'] = ['option.%s=%s'%(x[0], x[1]) for x in req['params']]
      if not clop['white']:
        clop['fcp'], clop['scp'] = clop['scp'], clop['fcp']
    else:
      if req['task_alive']:
        # Retry in 5 seconds
        raise Exception('no_games for request_clop.  waiting...')
      return req

  # Run cutechess-cli binary
  if regression_test:
    cmd = ['cutechess_regression_test.sh']
  else:
    idx = cmd.index('_clop_')
    cmd = cmd[:idx] + clop['fcp'] + cmd[idx+1:]
    idx = cmd.index('_clop_')
    cmd = cmd[:idx] + clop['scp'] + cmd[idx+1:]

  print cmd
  p = subprocess.Popen(cmd, stdout=subprocess.PIPE, universal_newlines=True, bufsize=1, close_fds=not IS_WINDOWS)

  try:
    req = run_game(p, remote, result, clop, clop_tuning, tc_limit)
    p.wait()

    if p.returncode != 0:
      raise Exception('Non-zero return code: %d' % (p.returncode))
  except:
    traceback.print_exc(file=sys.stderr)
    try:
      kill_process(p)
      p.wait()
    except:
      pass

  return req

clop_threads = {'active': True}
def run_clop(*args):
  while clop_threads['active']:
    try:
      if not launch_cutechess(*args)['task_alive']:
        clop_threads['active'] =  False
    except:
      sys.stderr.write('Exception while running clop task:\n')
      traceback.print_exc(file=sys.stderr)
      time.sleep(5)
  sys.stderr.write('WARNING Exiting clop worker thread\n')

def run_games(worker_info, password, remote, run, task_id):
  task = run['tasks'][task_id]
  result = {
    'username': worker_info['username'],
    'password': password,
    'run_id': str(run['_id']),
    'task_id': task_id,
    'stats': {'wins':0, 'losses':0, 'draws':0, 'crashes':0, 'time_losses':0},
  }

  # Have we run any games on this task yet?
  global old_stats
  old_stats = task.get('stats', {'wins':0, 'losses':0, 'draws':0, 'crashes':0, 'time_losses':0})
  result['stats']['crashes'] = old_stats.get('crashes', 0)
  result['stats']['time_losses'] = old_stats.get('time_losses', 0)
  games_remaining = task['num_games'] - (old_stats['wins'] + old_stats['losses'] + old_stats['draws'])
  if games_remaining <= 0:
    raise Exception('No games remaining')

  book = run['args']['book']
  book_depth = run['args']['book_depth']
  new_options = run['args']['new_options']
  base_options = run['args']['base_options']
  threads = int(run['args']['threads'])
  regression_test = run['args'].get('regression_test', False)
  clop_tuning = 'clop' in run['args']
  binaries_url = run.get('binaries_url', '')
  repo_url = run['args'].get('tests_repo', FISHCOOKING_URL)
  games_concurrency = int(worker_info['concurrency']) / threads

  # Format options according to cutechess syntax
  def parse_options(s):
    results = []
    chunks = s.split('=')
    if len(chunks) == 0:
      return results 
    param = chunks[0]
    for c in chunks[1:]:
      val = c.split()
      results.append('option.%s=%s' % (param, val[0]))
      param = ' '.join(val[1:])
    return results
 
  new_options = parse_options(new_options)
  base_options = parse_options(base_options)

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
    setup_engine(new_engine, binaries_url, worker_dir, run['args']['resolved_new'], repo_url, worker_info['concurrency'])
    if not regression_test:
      setup_engine(base_engine, binaries_url, worker_dir, run['args']['resolved_base'], repo_url, worker_info['concurrency'])
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
  base_nps = verify_signature(new_engine, run['args']['new_signature'], remote, result, games_concurrency)
  if not regression_test:
    verify_signature(base_engine, run['args']['base_signature'], remote, result, games_concurrency)

  # Benchmark to adjust cpu scaling
  scaled_tc, tc_limit = adjust_tc(run['args']['tc'], base_nps, int(worker_info['concurrency']))
  result['nps'] = base_nps

  # Handle book or pgn file
  pgn_cmd = []
  book_cmd = []
  if book.endswith('.pgn') or book.endswith('.epd'):
    plies = 2 * int(book_depth)
    pgn_cmd = ['-openings', 'file=%s' % (book), 'format=%s' % (book[-3:]), 'order=random', 'plies=%d' % (plies)]
  else:
    book_cmd = ['book=%s' % (book), 'bookdepth=%s' % (book_depth)]

  if not regression_test:
    print 'Running %s vs %s' % (run['args']['new_tag'], run['args']['base_tag'])
  else:
    print 'Running regression test of %s' % (run['args']['new_tag'])

  if clop_tuning:
    worker_threads = games_concurrency
    games_to_play = 1
    games_concurrency = 1
    pgnout = []
  else:
    worker_threads = 1
    games_to_play = games_remaining
    pgnout = ['-pgnout', 'results.pgn']

  # Run cutechess-cli binary
  cmd = [ cutechess, '-repeat', '-rounds', str(games_to_play), '-tournament', 'gauntlet'] + pgnout + \
        ['-resign', 'movecount=3', 'score=400', '-draw', 'movenumber=34',
         'movecount=8', 'score=20', '-concurrency', str(games_concurrency)] + pgn_cmd + \
        ['-engine', 'name=stockfish', 'cmd=stockfish'] + new_options + \
        ['_clop_','-engine', 'name=base', 'cmd=base'] + base_options + \
        ['_clop_','-each', 'proto=uci', 'option.Threads=%d' % (threads), 'tc=%s' % (scaled_tc)] + book_cmd

  payload = (cmd, remote, result, clop_tuning, regression_test, tc_limit * games_to_play / min(games_to_play, games_concurrency))

  if worker_threads == 1:
    launch_cutechess(*payload)
  else:
    clop_threads['active'] = True
    th = [threading.Thread(target=run_clop, args=payload) for _ in range(worker_threads)]
    for t in th:
      t.start()

    # Wait for all the worker threads to finish
    for t in th:
      # Super long timeout is a workaround for signal handling when doing thread.join
      # See http://stackoverflow.com/questions/631441/interruptible-thread-join-in-python
      t.join(2 ** 31)
