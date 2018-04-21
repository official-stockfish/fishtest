import unittest
import datetime

from pyramid import testing

from fishtest.rundb import RunDb

from fishtest.views import signup
from fishtest.views import login

from fishtest.api import stop_run

  
class Create10UsersTest(unittest.TestCase):

  def setUp(self):
    rundb= RunDb()
    self.request = testing.DummyRequest(
            params={'form.submitted': True, 'username': 'JoeUser',
              'password': 'secret', 'password2': 'secret', 'email': 'joe@user.net'},
            userdb=rundb.userdb
            )

    config = testing.setUp(request=self.request)

  def tearDown(self):
    testing.tearDown()

  def test_create_users(self):
    with testing.testConfig() as config:
      config.add_route('login', '/login')
      config.add_route('signup', '/signup')
      print(signup(self.request))
      userc= {}
      userc['cpu_hours'] = 12345
      userc['username'] = 'JoeUser'
      self.request.userdb.user_cache.insert(userc)


class Create50LoginTest(unittest.TestCase):

  def setUp(self):
    rundb= RunDb()
    self.params = {'form.submitted': True, 'username': 'JoeUser', 'password': 'badsecret'}
    self.request = testing.DummyRequest(
            params=self.params, userdb=rundb.userdb)

    config = testing.setUp(request=self.request)

  def tearDown(self):
    testing.tearDown()

  def test_logins(self):
    with testing.testConfig() as config:
      config.add_route('login', '/login')
      r= login(self.request)
      self.assertFalse('found' in str(r))

      self.params['password'] = 'secret'
      r= login(self.request)
      # Still blocked:
      self.assertFalse('found' in str(r))

      # Unblock:
      user = self.request.userdb.get_user('JoeUser')
      user['blocked'] = False
      self.request.userdb.save_user(user)
      r= login(self.request)
      self.assertTrue('found' in str(r))

  
rundb = None

class Create90APITest(unittest.TestCase):
  def setUp(self):
    global rundb
    rundb= RunDb()
    run_id = rundb.new_run('master', 'master', 100000, '100+0.01', 'book', 10, 1, '', '',
                           username='travis', tests_repo='travis', start_time=datetime.datetime.utcnow())
    json_params= {'username': 'JoeUser', 'password': 'secret', 'run_id': run_id, 'message': 'travis'}
    self.request = testing.DummyRequest(
            json_body=json_params,
            method='POST',
            rundb=rundb,
            userdb=rundb.userdb,
            actiondb=rundb.actiondb
            )

    config = testing.setUp(request=self.request)

  def tearDown(self):
    self.request.userdb.users.delete_many({'username': 'JoeUser'})
    self.request.userdb.user_cache.delete_many({'username': 'JoeUser'})
    # Shutdown flush thread:
    global rundb
    rundb.stop()
    testing.tearDown()

  def test_stop_run(self):
    with testing.testConfig() as config:
      config.add_route('api_stop_run', '/api/stop_run')
      self.assertEqual(stop_run(self.request), '{}')
      self.assertEqual(self.request.rundb.get_run(self.request.json_body['run_id'])['stop_reason'], 'travis')
      

if __name__ == "__main__":
  unittest.main()
