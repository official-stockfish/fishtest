import os
import sys
from bson.objectid import ObjectId
from pymongo import ASCENDING, DESCENDING

class ClopDb:
  def __init__(self, db):
    self.db = db
    self.clop = self.db['clop']

  def get_games(self, run_id = ''):
    if len(run_id) == 0:
      return self.clop.find(sort=[('_id', ASCENDING)])
    else:
      return self.clop.find({'run_id': run_id}, sort=[('_id', ASCENDING)])

  def get_game(self, game_id):
    return self.clop.find_one({'_id': ObjectId(game_id)})

  def remove_game(self, game_id):
    return self.clop.remove({'_id': ObjectId(game_id)}, True)

  def write_result(self, game_id, result):
    game = self.get_game(game_id)
    if game != None:
      game['result'] = result
      self.clop.save(game)
      os.system("kill -18 %d" % (game['pid']))

  def add_game(self, pid, run_id, seed, white, params):
    id = self.clop.insert({
      'pid': pid,
      'run_id': run_id,
      'task_id': '',
      'seed': seed,
      'white': white,
      'params': params,
      'result': '',
    })
    return id

  def request_game(self, run_id, task_id):
    for game in self.get_games(run_id):
      if len(game['task_id']) == 0:
        game['task_id'] = str(task_id)
        self.clop.save(game)
        return { 'game_id': str(game['_id']),
                 'seed': game['seed'],
                 'white': game['white'],
                 'params': game['params'] }
    else:
      return {'no_games': True}
