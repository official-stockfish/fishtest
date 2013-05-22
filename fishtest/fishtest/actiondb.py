import sys
from datetime import datetime
from pymongo import ASCENDING, DESCENDING

class ActionDb:
  def __init__(self, db):
    self.db = db
    self.actions = self.db['actions']
    self.actions.remove()

  def get_actions(self):
    return self.actions.find(sort=[('_id', DESCENDING)])

  def new_run(self, username, run):
    self._new_action(username, 'new_run', run)

  def modify_run(self, username, before, after):
    self._new_action(username, 'modify_run', {'before': before, 'after': after})

  def delete_run(self, username, run):
    self._new_action(username, 'delete_run', run)

  def stop_run(self, username, run):
    self._new_action(username, 'stop_run', run)

  def _new_action(self, username, action, data):
    self.actions.insert({
      'username': username,
      'action': action,
      'data': data,
      'time': datetime.utcnow(),
    })
