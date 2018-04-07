import unittest

from pyramid import testing

from fishtest.rundb import RunDb

from fishtest.views import signup
from fishtest.views import login

  
class Create1UsersTest(unittest.TestCase):

  def setUp(self):
    rundb= RunDb()
    self.request = testing.DummyRequest(
            params= {'form.submitted': True, 'username': 'JoeUser', 'password': 'secret', 'email': 'joe@user.net'},
            userdb = rundb.userdb
            )

    config = testing.setUp(request = self.request)

  def tearDown(self):
    testing.tearDown()

  def test_create_users(self):
    with testing.testConfig() as config:
      config.add_route('login', '/login')
      config.add_route('signup', '/signup')
      print(signup(self.request))

  
class Create2LoginTest(unittest.TestCase):

  def setUp(self):
    rundb= RunDb()
    self.params= {'form.submitted': True, 'username': 'JoeUser', 'password': 'badsecret'}
    self.request = testing.DummyRequest(
            params= self.params, userdb = rundb.userdb)

    config = testing.setUp(request = self.request)

  def tearDown(self):
    testing.tearDown()

  def test_logins(self):
    with testing.testConfig() as config:
      config.add_route('login', '/login')
      r= login(self.request)
      self.assertFalse('found' in str(r))

      self.params['password'] = 'secret'
      r= login(self.request)
      self.assertTrue('found' in str(r))


if __name__ == "__main__":
  unittest.main()
