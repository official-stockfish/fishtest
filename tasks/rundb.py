import datetime, os
from bson.objectid import ObjectId
from pymongo import MongoClient, ASCENDING, DESCENDING

class RunDb:
  def __init__(self):
    # MongoDB server is assumed to be on the same machine, if not user should use
    # ssh with port forwarding to access the remote host.
    self.conn = MongoClient(os.getenv('FISHTEST_HOST') or 'localhost')
    self.db = self.conn['fishtest']
    self.runs = self.db['runs']

    self.chunk_size = 1000

  def generate_chunks(self, num_games):
    worker_results = []
    remaining = num_games
    while remaining > 0:
      chunk_size = min(self.chunk_size, remaining)
      worker_results.append({
        'chunk_size': chunk_size,
      })
      remaining -= chunk_size
    return worker_results

  def new_run(self, base_tag, new_tag, num_games, tc, book, book_depth,
              name='',
              info='',
              resolved_base='',
              resolved_new='',
              base_signature='',
              new_signature='',
              start_time=None):
    if start_time == None:
      start_time = datetime.datetime.now()

    id = self.runs.insert({
      'args': {
        'base_tag': base_tag,
        'new_tag': new_tag,
        'num_games': num_games,
        'tc': tc,
        'book': book,
        'book_depth': book_depth,
        'resolved_base': resolved_base,
        'resolved_new': resolved_new,
        'name': name,
        'info': info,
        'base_signature': base_signature,
        'new_signature': new_signature,
      },
      'start_time': start_time,
      # Will be filled in by workers, indexed by chunk-id
      'worker_results': self.generate_chunks(num_games),
      # Aggregated results
      'results': { 'wins': 0, 'losses': 0, 'draws': 0 },
      'results_stale': False,
    })

    return id

  def get_run(self, id):
    return self.runs.find_one({'_id': ObjectId(id)})

  def get_runs(self, skip=0, limit=0):
    runs = []
    for run in self.runs.find(skip=skip, limit=limit, sort=[('start_time', DESCENDING)]):
      runs.append(run)
    return runs

  def update_run_results(self, id, chunk, wins, losses, draws):
    run = self.get_run(id)
    run['worker_results'][chunk]['stats'] = {
      'wins': wins,
      'losses': losses,
      'draws': draws
    }
    run['results_stale'] = True
    self.runs.save(run)

  def get_results(self, run):
    if not run['results_stale']:
      return run['results']

    results = { 'wins': 0, 'losses': 0, 'draws': 0 }
    for chunk in run['worker_results']:
      if 'stats' in chunk:
        stats = chunk['stats']
        results['wins'] += stats['wins']
        results['losses'] += stats['losses']
        results['draws'] += stats['draws']

    run['results_stale'] = False
    run['results'] = results
    self.runs.save(run)

    return results
