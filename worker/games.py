from __future__ import absolute_import

import datetime
import json
import os
import glob
import stat
import random
import subprocess
import shutil
import sys
import tempfile
import threading
import time
import traceback
import platform
import struct
import zipfile
import requests
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

HTTP_TIMEOUT = 15.0

FISHCOOKING_URL = 'https://github.com/mcostalba/FishCooking'
ARCH = 'ARCH=x86-64-modern' if is_64bit() else 'ARCH=x86-32'
EXE_SUFFIX = ''
MAKE_CMD = 'make COMP=gcc ' + ARCH

if IS_WINDOWS:
  EXE_SUFFIX = '.exe'
  MAKE_CMD = 'make COMP=mingw ' + ARCH

def printout(s):
  print s
  sys.stdout.flush()

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
    printout('Verifying signature of %s ...' % (os.path.basename(engine)))
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
      message = 'Wrong bench in %s Expected: %s Got: %s' % (os.path.basename(engine), signature, bench_sig)
      payload['message'] = message
      requests.post(remote + '/api/stop_run', data=json.dumps(payload), headers={'Content-type': 'application/json'}, timeout=HTTP_TIMEOUT)
      raise Exception(message)

  finally:
    if concurrency > 1:
      busy_process.communicate('quit\n')

  return bench_nps

def cleanup(item, testing_dir):
  """Remove corrupted opening books"""
  target_path = os.path.join(testing_dir, item)
  if os.path.exists(target_path):
    stat_info = os.stat(target_path)
  else:
    return True
  if stat_info.st_size == 0:
    os.remove(target_path)
    return False
  else:
    return True

def setup(item, testing_dir):
  """Download item from FishCooking to testing_dir"""
  tree = requests.get(github_api(FISHCOOKING_URL) + '/git/trees/setup', timeout=HTTP_TIMEOUT).json()
  for blob in tree['tree']:
    if blob['path'] == item:
      printout('Downloading %s ...' % (item))
      blob_json = requests.get(blob['url'], timeout=HTTP_TIMEOUT).json()
      while not cleanup(item, testing_dir):
        blob_request = requests.get(blob['url'], timeout=HTTP_TIMEOUT)
        blob_json = blob_request.json()
        if blob_request.status_code == requests.codes.ok:
          break
        sleep(5)
      with open(os.path.join(testing_dir, item), 'wb+') as f:
        f.write(b64decode(blob_json['content']))
      break
  else:
    raise Exception('Item %s not found' % (item))

def setup_engine(destination, worker_dir, sha, repo_url, concurrency):
  if os.path.exists(destination): os.remove(destination)
  """Download and build sources in a temporary directory then move exe to destination"""
  tmp_dir = tempfile.mkdtemp()
  
  try:
    os.chdir(tmp_dir)
    with open('sf.gz', 'wb+') as f:
      f.write(requests.get(github_api(repo_url) + '/zipball/' + sha, timeout=HTTP_TIMEOUT).content)
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
      subprocess.check_call(MAKE_CMD + ' -j %s' % (concurrency) + ' profile-build', shell=True)
      try: # try/pass needed for backwards compatibility with older stockfish, where 'make strip' fails under mingw.
        subprocess.check_call(MAKE_CMD + ' -j %s' % (concurrency) + ' strip', shell=True)
      except:
        pass
      
      
    shutil.move('stockfish'+ EXE_SUFFIX, destination)
  except:
    raise Exception('Failed to setup engine for %s' % (sha))
  finally:
    os.chdir(worker_dir)
    shutil.rmtree(tmp_dir)
    
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
    scaled_tc += '+%.2f' % (increment * factor)
    tc_limit += increment * factor * 200
  if num_moves > 0:
    scaled_tc = '%d/%s' % (num_moves, scaled_tc)
    tc_limit *= 100.0 / num_moves

  printout('CPU factor : %f - tc adjusted to %s' % (factor, scaled_tc))
  return scaled_tc, tc_limit

def enqueue_output(out, queue):
  for line in iter(out.readline, b''):
    queue.put(line)
  out.close()

w_params = None
b_params = None

def run_game(p, remote, result, spsa, spsa_tuning, tc_limit):
  global old_stats
  failed_updates = 0

  q = Queue()
  t = threading.Thread(target=enqueue_output, args=(p.stdout, q))
  t.daemon = True
  t.start()

  end_time = datetime.datetime.now() + datetime.timedelta(seconds=tc_limit)
  printout('TC limit '+str(tc_limit)+' End time: '+str(end_time))

  while datetime.datetime.now() < end_time:
    try: line = q.get_nowait()
    except Empty:
      if p.poll() != None:
        break
      time.sleep(1)
      continue

    sys.stdout.write(line)
    sys.stdout.flush()

    # Have we reached the end of the match?  Then just exit
    if 'Finished match' in line:
      printout('Finished match cleanly')
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

      if spsa_tuning:
        spsa['wins'] = wld[0]
        spsa['losses'] = wld[1]
        spsa['draws'] = wld[2]

      try:
        t0 = datetime.datetime.utcnow()
        req = requests.post(remote + '/api/update_task', data=json.dumps(result), headers={'Content-type': 'application/json'}, timeout=HTTP_TIMEOUT).json()
        failed_updates = 0
        printout("Task updated successfully in "+str((datetime.datetime.utcnow()-t0).total_seconds())+"s")

        if not req['task_alive']:
          # This task is no longer neccesary
          printout('Server told us task is no longer needed')
          kill_process(p)
          return req

      except:
        sys.stderr.write('Exception from calling update_task:\n')
        traceback.print_exc(file=sys.stderr)
        failed_updates += 1
        if failed_updates > 5:
          printout('Too many failed update attempts')
          kill_process(p)
          break
        time.sleep(random.randint(failed_updates*failed_updates, 4 * failed_updates*failed_updates))

  if datetime.datetime.now() >= end_time:
    printout(datetime.datetime.now()+' is past end time '+end_time)
    kill_process(p)

  return { 'task_alive': True }

def launch_cutechess(cmd, remote, result, spsa_tuning, games_to_play, tc_limit):
  spsa = {
    'w_params': [],
    'b_params': [],
    'num_games': games_to_play,
  }

  if spsa_tuning:
    # Request parameters for next game
    req = requests.post(remote + '/api/request_spsa', data=json.dumps(result), headers={'Content-type': 'application/json'}, timeout=HTTP_TIMEOUT).json()

    global w_params, b_params
    w_params = req['w_params']
    b_params = req['b_params']

    result['spsa'] = spsa
  else:
    w_params = []
    b_params = []

  # Run cutechess-cli binary
  idx = cmd.index('_spsa_')
  cmd = cmd[:idx] + ['option.%s=%d'%(x['name'], round(x['value'])) for x in w_params] + cmd[idx+1:]
  idx = cmd.index('_spsa_')
  cmd = cmd[:idx] + ['option.%s=%d'%(x['name'], round(x['value'])) for x in b_params] + cmd[idx+1:]

  printout(cmd)
  p = subprocess.Popen(cmd, stdout=subprocess.PIPE, universal_newlines=True, bufsize=1, close_fds=not IS_WINDOWS)

  try:
    return run_game(p, remote, result, spsa, spsa_tuning, tc_limit)
  except:
    traceback.print_exc(file=sys.stderr)
    try:
      printout('Exception running games')
      kill_process(p)
    except:
      pass

  return { 'task_alive': False }

def run_games(worker_info, password, remote, run, task_id):
  task = run['tasks'][task_id]
  result = {
    'unique_key': worker_info['unique_key'],
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
  spsa_tuning = 'spsa' in run['args']
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

  # clean up old engines (keeping the 25 most recent)
  engines = glob.glob(os.path.join(testing_dir, 'stockfish_*' + EXE_SUFFIX))
  if len(engines) > 25:
    engines.sort(key=os.path.getmtime)
    for old_engine in engines[:len(engines)-25]:
      os.remove(old_engine)

  # create new engines
  sha_new = run['args']['resolved_new']
  sha_base = run['args']['resolved_base']
  new_engine_name = 'stockfish_' + sha_new
  base_engine_name = 'stockfish_' + sha_base

  new_engine = os.path.join(testing_dir, new_engine_name + EXE_SUFFIX)
  base_engine = os.path.join(testing_dir, base_engine_name + EXE_SUFFIX)
  cutechess = os.path.join(testing_dir, 'cutechess-cli' + EXE_SUFFIX)

  # Build from sources new and base engines as needed
  if not os.path.exists(new_engine):
    setup_engine(new_engine, worker_dir, sha_new, repo_url, worker_info['concurrency'])
  if not os.path.exists(base_engine):
    setup_engine(base_engine, worker_dir, sha_base, repo_url, worker_info['concurrency'])

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
  base_nps = verify_signature(new_engine, run['args']['new_signature'], remote, result, games_concurrency * threads)
  verify_signature(base_engine, run['args']['base_signature'], remote, result, games_concurrency * threads)

  # Benchmark to adjust cpu scaling
  scaled_tc, tc_limit = adjust_tc(run['args']['tc'], base_nps, int(worker_info['concurrency']))
  result['nps'] = base_nps

  # Handle book or pgn file
  pgn_cmd = []
  book_cmd = []
  if book_depth <= 0:
    pass
  elif book.endswith('.pgn') or book.endswith('.epd'):
    plies = 2 * int(book_depth)
    pgn_cmd = ['-openings', 'file=%s' % (book), 'format=%s' % (book[-3:]), 'order=random', 'plies=%d' % (plies)]
  else:
    book_cmd = ['book=%s' % (book), 'bookdepth=%s' % (book_depth)]

  printout('Running %s vs %s' % (run['args']['new_tag'], run['args']['base_tag']))

  if spsa_tuning:
    games_to_play = games_concurrency * 2
    pgnout = []
  else:
    games_to_play = games_remaining
    pgnout = ['-pgnout', 'results.pgn']

  threads_cmd=[]
  if not any("Threads" in s for s in new_options + base_options):
    threads_cmd = ['option.Threads=%d' % (threads)]

  # If nodestime is being used, give engines extra grace time to 
  # make time losses virtually impossible
  nodestime_cmd=[]
  if any ("nodestime" in s for s in new_options + base_options):
    nodestime_cmd = ['timemargin=10000']

  while games_remaining > 0:
    # Run cutechess-cli binary
    cmd = [ cutechess, '-repeat', '-rounds', str(games_to_play), '-tournament', 'gauntlet'] + pgnout + \
          ['-srand', "%d" % struct.unpack("<L", os.urandom(struct.calcsize("<L")))] + \
          ['-resign', 'movecount=3', 'score=400', '-draw', 'movenumber=34',
           'movecount=8', 'score=20', '-concurrency', str(games_concurrency)] + pgn_cmd + \
          ['-engine', 'name=stockfish', 'cmd=%s' % (new_engine_name)] + new_options + ['_spsa_'] + \
          ['-engine', 'name=base', 'cmd=%s' % (base_engine_name)] + base_options + ['_spsa_'] + \
          ['-each', 'proto=uci', 'tc=%s' % (scaled_tc)] + nodestime_cmd + threads_cmd + book_cmd

    task_status = launch_cutechess(cmd, remote, result, spsa_tuning, games_to_play, tc_limit * games_to_play / min(games_to_play, games_concurrency))
    if not task_status.get('task_alive', False):
      break

    old_stats = result['stats'].copy()
    games_remaining -= games_to_play
