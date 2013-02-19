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

  use_temp_dir = False
  if use_temp_dir:
    # Create temporary directory, and copy everything in.  This is to allow multiple
    # tasks to run at once
    working_dir = tempfile.mkdtemp()
    stockfish_dir = os.path.join(working_dir, 'stockfish')
    testing_dir = os.path.join(working_dir, 'testing')
    sh.cp('-r', os.getenv('STOCKFISH_DIR'), stockfish_dir)
    sh.cp('-r', os.getenv('FISHTEST_DIR'), testing_dir)
  else:
    stockfish_dir = os.getenv('STOCKFISH_DIR')
    testing_dir = os.getenv('FISHTEST_DIR')

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

  state = {'wins':0, 'losses':0, 'draws':0}

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

  if use_temp_dir:
    sh.rm('-rf', working_dir)

  return state
