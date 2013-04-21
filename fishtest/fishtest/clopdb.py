import sys
from bson.objectid import ObjectId
from pymongo import ASCENDING, DESCENDING

class ClopDb:
  def __init__(self, db):
    self.db = db
    self.clop = self.db['clop']

  def get_games(self):
    return self.clop.find(sort=[('_id', ASCENDING)])

  def get_game(self, game_id):
    return self.clop.find_one({'_id': ObjectId(game_id)})

  def remove_game(self, game_id):
    return self.clop.remove({'_id': ObjectId(game_id)}, True)

  def write_result(self, game_id, result):
    self.clop.update({ '_id': ObjectId(game_id) }, { '$set': { 'result': result }, })

  def add_game(self, pid, machine, seed, params):
    id = self.clop.insert({
      'pid': pid,
      'machine': machine,
      'seed': seed,
      'params': params,
      'result': '',
      'started': False,
    })
    return id

  def request_game(self):
    for game in self.get_games():
      if not game.get('started', True):
        game['started'] = True
        self.clop.save(game)
        return { 'game_id': str(game['_id']),
                 'seed': game['seed'],
                 'params': game['params'] }
    else:
      return {'game_waiting': False}

