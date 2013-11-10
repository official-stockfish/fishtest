import os
import sys
from bson.objectid import ObjectId
from pymongo import ASCENDING, DESCENDING

class ClopDb:
  def __init__(self, db, clop_socket):
    self.db = db
    self.clop = self.db['clop']
    self.clop_socket = clop_socket

  def get_games(self, run_id = '', task_id = ''):
    run_id = str(run_id)
    task_id = str(task_id)
    if len(run_id) == 0:
      return self.clop.find(sort=[('_id', ASCENDING)])
    elif len(task_id) == 0:
      return self.clop.find({'run_id': run_id}, sort=[('_id', ASCENDING)])
    else:
      return self.clop.find({'run_id': run_id, 'task_id': task_id},
                            sort=[('_id', ASCENDING)])

  def get_game(self, game_id):
    return self.clop.find_one({'_id': ObjectId(game_id)})

  def remove_game(self, game_id):
    return self.clop.remove({'_id': ObjectId(game_id)}, True)

  def stop_games(self, run_id = '', task_id = ''):
    print 'clop stop_games %s %s' % (run_id, task_id)
    for game in self.get_games(run_id, task_id):
      if len(game['result']) == 0:
        self.write_result(game['_id'], 'stop')

  def write_result(self, game_id, result):
    game = self.get_game(game_id)
    if game != None:
      game['result'] = result
      self.clop.save(game)
      self.clop_socket.send_unicode(str(game_id))

  def add_game(self, run_id, seed, white, params):
    id = self.clop.insert({
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
      return {'no_games': True,
              'task_alive': True}
