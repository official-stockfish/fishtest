from __future__ import absolute_import

from tasks.celery import celery
import os
import sh

@celery.task
def run_games(base_branch, new_branch, num_games, tc):
  stockfish_dir = os.getenv('STOCKFISH_DIR')
  testing_dir = os.getenv('FISHTEST_DIR')

  sh.cd(os.path.join(stockfish_dir, 'src'))
  sh.git.fetch()

  # Build base
  sh.git.checkout(base_branch)
  sh.make('clean')
  sh.make('build', 'ARCH=x86-64')
  sh.cp('stockfish', os.path.join(testing_dir, 'base'))

  # Build new
  sh.git.checkout(new_branch)
  sh.make('clean')
  sh.make('build', 'ARCH=x86-64')
  sh.cp('stockfish', testing_dir)

  sh.cd(testing_dir)

  # Run cutechess
  sh.Command('./timed.sh')(num_games, tc)
