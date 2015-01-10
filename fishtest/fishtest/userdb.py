import sys
from pymongo import ASCENDING, DESCENDING

class UserDb:
  def __init__(self, db):
    self.db = db
    self.users = self.db['users']
    self.user_cache = self.db['user_cache']
    self.flag_cache = self.db['flag_cache']

  def init_collection(self):
    self.users.create_index('username', unique=True)

  def authenticate(self, username, password):
    user = self.users.find_one({'username': username})
    if not user or user['password'] != password:
      sys.stderr.write('Invalid login: "%s" "%s"\n' % (username, password))
      return {'error': 'Invalid password'}

    return {'username': username, 'authenticated': True}

  def get_users(self):
    return self.users.find(sort=[('_id', ASCENDING)])

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
      self.users.insert({
        'username': username,
        'password': password,
        'email': email,
        'groups': [],
        'tests_repo': ''
      })
      return True
    except:
      return False

  def get_machine_limit(self, username):
    user = self.users.find_one({'username': username})
    if user and 'machine_limit' in user:
      return user['machine_limit']
    return 4

  def is_blocked(self, worker_info):
    # TODO: hook the blocked info into the database
    blocked = [ 'garry561', 'EthanOConnor', 'IamLupo' ]
    if worker_info['remote_addr'] in blocked or worker_info['username'] in blocked:
      return True
    return False
