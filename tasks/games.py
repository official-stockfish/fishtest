from __future__ import absolute_import

from tasks.celery import celery
from tasks.rundb import RunDb
import os
import sh
import tempfile
import zipfile
from urllib import urlretrieve
from zipfile import ZipFile

FISHCOOKING_URL = 'https://api.github.com/repos/mcostalba/FishCooking'

def verify_signature(engine, signature):
  bench_sig = ''

  def bench_output(line):
    if 'Nodes searched' in line:
      bench_sig = line.split(': ')[1]

  sh.Command(engine)(bench, _out=bench_output).wait()
  if bench_sig != signature:
    raise Exception('Wrong bench in ' + engine)


# Download and build sources in a temporary directory then move exe to destination
def build(sha, destination):
  working_dir = tempfile.mkdtemp()
  sh.cd(working_dir)
  urlretrieve(FISHCOOKING_URL + '/zipball/' + sha, 'sf.zip')
  zip_file = ZipFile('sf.zip')
  zip_file.extractall()
  for name in zip_file.namelist():
    if name.endswith('/src/'):
      src_dir = name
  sh.cd(src_dir)
  sh.make('build', 'ARCH=x86-64-modern')
  sh.mv('stockfish', destination)
  sh.cd('/tmp')
  sh.rm('-r', working_dir)

@celery.task
def run_games(run_id, run_chunk):
  rundb = RunDb()
  run = rundb.get_run(run_id)

  testing_dir = os.getenv('FISHTEST_DIR')

  # Download and build base and new
  build(run['args']['resolved_base'], os.path.join(testing_dir, 'base'))
  build(run['args']['resolved_new'] , os.path.join(testing_dir, 'stockfish'))

  sh.cd(testing_dir)
  sh.rm('-f', 'results.pgn')

  state = {'wins':0, 'losses':0, 'draws':0}

  # Verify signatures are correct
  if len(run['args']['base_signature']) > 0:
    verify_signature('base', run['args']['base_signature'])

  if len(run['args']['new_signature']) > 0:
    verify_signature('stockfish', run['args']['new_signature'])

  def process_output(line):
    # Parse line like this:
    # Score of Stockfish  130212 64bit vs base: 1701 - 1715 - 6161  [0.499] 9577
    if 'Score' in line:
      chunks = line.split(':')
      chunks = chunks[1].split()
      state['wins'] = int(chunks[0])
      state['losses'] = int(chunks[2])
      state['draws'] = int(chunks[4])

      rundb.update_run_results(run_id, run_chunk, **state)

  # Run cutechess
  chunk_size = run['worker_results'][run_chunk]['chunk_size']
  p = sh.Command('./timed.sh')(chunk_size, run['args']['tc'], _out=process_output)
  if p.exit_code() != 0:
    raise Exception(p.stderr())

  return state
