import sys
import time
import threading

from datetime import datetime
from pymongo import ASCENDING, DESCENDING

class UserDb:
  def __init__(self, db):
    self.db = db
    self.users = self.db['users']
    self.user_cache = self.db['user_cache']
    self.top_month = self.db['top_month']
    self.old_user_cache = self.db['old_user_cache']
    self.flag_cache = self.db['flag_cache']

  def init_collection(self):
    self.users.create_index('username', unique=True)

  def authenticate(self, username, password):
    user = self.users.find_one({'username': username})
    if not user or user['password'] != password:
      sys.stderr.write('Invalid login: "%s" "%s"\n' % (username, password))
      return {'error': 'Invalid password'}
    if 'blocked' in user and user['blocked']:
      sys.stderr.write('Blocked login: "%s" "%s"\n' % (username, password))
      return {'error': 'Blocked'}

    return {'username': username, 'authenticated': True}

  def get_users(self):
    return self.users.find(sort=[('_id', ASCENDING)])
  
  # Cache pending for 60s
  last_pending_time = 0
  last_pending = None
  pending_lock = threading.Lock()

  def get_pending(self):
    with self.pending_lock:
      if time.time() > self.last_pending_time + 60:
        self.last_pending = list(self.users.find({'blocked': True}, sort=[('_id', ASCENDING)]))
        self.last_pending_time = time.time()
      return self.last_pending

  def get_user(self, username):
    return self.users.find_one({'username': username})

  def get_user_groups(self, username):
    user = self.users.find_one({'username': username})
    if user:
      groups = user['groups']
      # Everyone is in this group by default
      groups.append('group:admins')
      return groups

  def add_user_group(self, username, group):
    user = self.users.find_one({'username': username})
    user['groups'].append(group)
    self.users.save(user)

  def create_user(self, username, password, email):
    try:
      if self.users.find_one({'username': username}):
        return False
      self.users.insert({
        'username': username,
        'password': password,
        'registration_time': datetime.utcnow(),
        'blocked': True,
        'email': email,
        'groups': [],
        'tests_repo': ''
      })
      self.last_pending_time = 0

      return True
    except:
      return False
  
  def save_user(self, user):
    self.users.save(user)
    self.last_pending_time = 0

  def get_machine_limit(self, username):
    user = self.users.find_one({'username': username})
    if user and 'machine_limit' in user:
      return user['machine_limit']
    return 4

