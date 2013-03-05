from __future__ import absolute_import

import json
import os
import requests
import sh
import sys
import tempfile
import time
import traceback
import zipfile
from base64 import b64decode
from urllib2 import urlopen, HTTPError
from zipfile import ZipFile

FISHCOOKING_URL = 'https://api.github.com/repos/mcostalba/FishCooking'

def verify_signature(engine, signature):
  bench_sig = ''

  for line in sh.Command(engine)('bench', _iter='err'):
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
  """If we don't have the item in testing_dir, download it from FishCooking"""
  if len(item) > 0:
    if not os.path.exists(os.path.join(testing_dir, item)):
      found = False
      tree = json.loads(robust_download(FISHCOOKING_URL + '/git/trees/setup'))
      for blob in tree['tree']:
        if blob['path'] == item:
          found = True
          blob_json = json.loads(robust_download(blob['url']))
          with open(os.path.join(testing_dir, item), 'w') as f:
            f.write(b64decode(blob_json['content']))
      if not found:
        raise Exception('Item %s not found' % (item))

def build(sha, destination, concurrency):
  """Download and build sources in a temporary directory then move exe to destination"""
  working_dir = tempfile.mkdtemp()
  sh.cd(working_dir)

  with open('sf.gz', 'w') as f:
    f.write(robust_download(FISHCOOKING_URL + '/zipball/' + sha))
  zip_file = ZipFile('sf.gz')
  zip_file.extractall()

  for name in zip_file.namelist():
    if name.endswith('/src/'):
      src_dir = name
  sh.cd(src_dir)
  sh.make('build', '-j' + str(concurrency), 'ARCH=x86-64-modern')
  sh.mv('stockfish', destination)
  sh.cd(os.path.expanduser('~/.'))
  sh.rm('-r', working_dir)

def upload_stats(remote, username, password, run_id, task_id, stats):
  payload = {
    'username': username,
    'password': password,
    'run_id': str(run_id),
    'task_id': task_id,
    'stats': stats,
  }
  try:
    requests.post(remote + '/api/update_task', data=json.dumps(payload))
  except:
    sys.stderr.write('Exception from calling update_task:\n')
    traceback.print_exc(file=sys.stderr)

def run_games(testing_dir, worker_info, password, remote, run, task_id):
  task = run['tasks'][task_id]

  stats = {'wins':0, 'losses':0, 'draws':0}

  # Have we run any games on this task yet?
  old_stats = task.get('stats', {'wins':0, 'losses':0, 'draws':0})
  games_remaining = task['num_games'] - (old_stats['wins'] + old_stats['losses'] + old_stats['draws'])
  if games_remaining <= 0:
    return 'No games remaining'

  book = run['args'].get('book', 'varied.bin')
  book_depth = run['args'].get('book_depth', '10')

  setup(book, testing_dir)
  setup('cutechess-cli.sh', testing_dir)

  # Download and build base and new
  build(run['args']['resolved_base'], os.path.join(testing_dir, 'base'), worker_info['concurrency'])
  build(run['args']['resolved_new'] , os.path.join(testing_dir, 'stockfish'), worker_info['concurrency'])

  sh.cd(testing_dir)
  sh.rm('-f', 'results.pgn')

  # Verify signatures are correct
  if len(run['args']['base_signature']) > 0:
    verify_signature('./base', run['args']['base_signature'])

  if len(run['args']['new_signature']) > 0:
    verify_signature('./stockfish', run['args']['new_signature'])

  def process_output(line):
    # Parse line like this:
    # Score of Stockfish  130212 64bit vs base: 1701 - 1715 - 6161  [0.499] 9577
    if 'Score' in line:
      chunks = line.split(':')
      chunks = chunks[1].split()
      stats['wins'] = int(chunks[0]) + old_stats['wins']
      stats['losses'] = int(chunks[2]) + old_stats['losses']
      stats['draws'] = int(chunks[4]) + old_stats['draws']

      upload_stats(remote, worker_info['username'], password, run['_id'], task_id, stats)

  # Run cutechess
  sh.chmod('+x', './cutechess-cli.sh')
  p = sh.Command('./cutechess-cli.sh')(games_remaining, run['args']['tc'], book, book_depth, worker_info['concurrency'], _out=process_output)
  p.wait()
  if p.exit_code != 0:
    raise Exception(p.stderr)
