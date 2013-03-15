import sys

class UserDb:
  def __init__(self, db):
    self.db = db
    self.users = self.db['users']

  def init_collection():
    self.user.create_index('username', unique=True)

  def authenticate(self, username, password):
    user = self.users.find_one({'username': username})
    if not user or user['password'] != password:
      sys.stderr.write('Invalid login: "%s" "%s"\n' % (username, password))
      return {'error': 'Invalid password'}

    return {'authenticated': True}

  def get_user_groups(self, username):
    user = self.users.find_one({'username': username})
    if user:
      return user['groups']

  def create_user(username, password, email):
    self.users.insert({
      'username': username,
      'password': password,
      'email': email,
    })
