from __future__ import absolute_import

from tasks.celery import celery
from tasks.rundb import RunDb
import os
import sh
import tempfile
import zipfile
import ujson
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
  
# Download and build sources in a temporary directory then move exe to destination
def build(sha, destination):
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
  sh.make('build', 'ARCH=x86-64-modern')
  sh.mv('stockfish', destination)
  sh.cd(os.path.expanduser('~/.'))
  sh.rm('-r', working_dir)

@celery.task
def run_games(run_id, run_chunk):
  rundb = RunDb()
  run = rundb.get_run(run_id)
  chunk = run['worker_results'][run_chunk]

  stats = {'wins':0, 'losses':0, 'draws':0}

  # Have we run any games on this chunk yet?
  old_stats = chunk.get('stats', {'wins':0, 'losses':0, 'draws':0})
  games_remaining = chunk['chunk_size'] - (old_stats['wins'] + old_stats['losses'] + old_stats['draws'])
  if games_remaining <= 0:
    return 'No games remaining'

  # Setup test environment
  testing_dir = os.getenv('FISHTEST_DIR')

  book = run['args'].get('book', 'varied.bin')
  book_depth = run['args'].get('book_depth', '10')
  if len(book) > 0:
    # If we don't already have the book, download it
    if not os.path.exists(os.path.join(testing_dir, book)):
      tree = ujson.loads(robust_download(FISHCOOKING_URL + '/git/trees/setup'))
      for blob in tree['tree']:
        if blob['path'] == book:
          with open(os.path.join(testing_dir, book), 'w') as f:
            f.write(robust_download(blob['url']))

  # Download and build base and new
  build(run['args']['resolved_base'], os.path.join(testing_dir, 'base'))
  build(run['args']['resolved_new'] , os.path.join(testing_dir, 'stockfish'))

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

      rundb.update_run_results(run_id, run_chunk, **stats)

  # Run cutechess
  p = sh.Command('./timed.sh')(games_remaining, run['args']['tc'], book, book_depth, _out=process_output)
  if p.exit_code != 0:
    raise Exception(p.stderr)

  return stats
