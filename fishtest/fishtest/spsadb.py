import os
import sys
from bson.objectid import ObjectId
from pymongo import ASCENDING, DESCENDING

class SpsaDb:
  def __init__(self, db):
    self.db = db
    self.spsa = self.db['spsa']

  def get_games(self, run_id = '', task_id = ''):
    run_id = str(run_id)
    task_id = str(task_id)
    if len(run_id) == 0:
      return self.spsa.find(sort=[('_id', ASCENDING)])
    elif len(task_id) == 0:
      return self.spsa.find({'run_id': run_id}, sort=[('_id', ASCENDING)])
    else:
      return self.spsa.find({'run_id': run_id, 'task_id': task_id},
                            sort=[('_id', ASCENDING)])

  def get_game(self, game_id):
    return self.spsa.find_one({'_id': ObjectId(game_id)})

  def remove_game(self, game_id):
    return self.spsa.remove({'_id': ObjectId(game_id)}, True)

  def stop_games(self, run_id = '', task_id = ''):
    print 'spsa stop_games %s %s' % (run_id, task_id)
    for game in self.get_games(run_id, task_id):
      if len(game['result']) == 0:
        self.write_result(game['_id'], 'stop')

  def write_result(self, game_id, result):
    game = self.get_game(game_id)
    if game != None:
      game['result'] = result
      self.spsa.save(game)

      # TODO - update spsa parameters

  def add_game(self, run_id, seed, white, params):
    id = self.spsa.insert({
      'run_id': run_id,
      'task_id': '',
      'seed': seed,
      'white': white,
      'params': params,
      'result': '',
    })
    return id

  def request_game(self, rundb, run_id, task_id):
    for game in self.get_games(run_id):
      if len(game['task_id']) == 0:
        game['task_id'] = str(task_id)
        self.spsa.save(game)
        return { 'game_id': str(game['_id']),
                 'seed': game['seed'],
                 'white': game['white'],
                 'params': game['params'] }

    run = rundb.get_run(run_id)
    if task_id >= len(run['tasks']):
      return {'task_alive': False}
    task = run['tasks'][task_id]
    if not task['active'] or not task['pending']:
      return {'task_alive': False}

    return {'task_alive': True}
