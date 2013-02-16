from __future__ import absolute_import

from tasks.celery import celery
from tasks.rundb import RunDb
import os
import sh
import tempfile

@celery.task
def run_games(run_id, run_chunk):
  rundb = RunDb()
  run = rundb.get_run(run_id)

  # Create temporary directory, and copy everything in.  This is to allow multiple
  # tasks to run at once
  working_dir = tempfile.mkdtemp()
  stockfish_dir = os.path.join(working_dir, 'stockfish')
  testing_dir = os.path.join(working_dir, 'testing')
  sh.cp('-r', os.getenv('STOCKFISH_DIR'), stockfish_dir)
  sh.cp('-r', os.getenv('FISHTEST_DIR'), testing_dir)

  sh.cd(os.path.join(stockfish_dir, 'src'))
  sh.git.fetch()

  # Build base
  sh.git.checkout(run['args']['resolved_base'])
  sh.make('clean')
  sh.make('build', 'ARCH=x86-64')
  sh.cp('stockfish', os.path.join(testing_dir, 'base'))

  # Build new
  sh.git.checkout(run['args']['resolved_new'])
  sh.make('clean')
  sh.make('build', 'ARCH=x86-64')
  sh.cp('stockfish', testing_dir)

  sh.cd(testing_dir)
  sh.rm('-f', 'results.pgn')

  # Run cutechess
  for line in sh.Command('./timed.sh')(run['worker_results'][run_chunk]['chunk_size'], run['args']['tc'], _iter=True):
    # Parse line like this:
    # Score of Stockfish  130212 64bit vs base: 1701 - 1715 - 6161  [0.499] 9577
    if 'Score' in line:
      chunks = line.split(':')
      chunks = chunks[1].split()
      state = {
        'wins': int(chunks[0]),
        'losses': int(chunks[2]),
        'draws': int(chunks[4]),
      }

      rundb.update_run_results(run_id, run_chunk, **state)

  sh.rm('-rf', working_dir)

  return state
