import datetime
import unittest
import base64
import zlib

from pyramid.testing import DummyRequest
from pyramid.httpexceptions import HTTPUnauthorized

from fishtest.api import ApiView, WORKER_VERSION
from util import get_rundb


class TestApi(unittest.TestCase):

  @classmethod
  def setUpClass(self):
    self.rundb = get_rundb()

    # Set up a run
    run_id = self.rundb.new_run('master', 'master', 1000, '10+0.01',
                                'book', 10, 1, '', '',
                                username='travis', tests_repo='travis',
                                start_time=datetime.datetime.utcnow())
    self.run_id = str(run_id)
    run = self.rundb.get_run(self.run_id)
    run['approved'] = True

    # Set up a task
    self.task_id = 3
    for i, task in enumerate(run['tasks']):
      if i is not self.task_id:
        run['tasks'][i]['pending'] = False

    self.rundb.buffer(run, True)

    # Set up an API user (a worker)
    self.username = 'JoeUserWorker'
    self.password = 'secret'
    self.remote_addr = '127.0.0.1'
    self.concurrency = 7

    self.worker_info = {
      'username': self.username,
      'password': self.password,
      'remote_addr': self.remote_addr,
      'concurrency': self.concurrency,
      'unique_key': 'unique key',
      'version': WORKER_VERSION
    }
    self.rundb.userdb.create_user(self.username, self.password, 'email@email.email')
    user = self.rundb.userdb.get_user(self.username)
    user['blocked'] = False
    user['machine_limit'] = 50
    self.rundb.userdb.save_user(user)

    self.rundb.userdb.user_cache.insert_one({
      'username': self.username,
      'cpu_hours': 0,
    })
    self.rundb.userdb.flag_cache.insert_one({
      'ip': self.remote_addr,
      'country_code': '??'
    })

  @classmethod
  def tearDownClass(self):
    self.rundb.runs.delete_one({ '_id': self.run_id })
    self.rundb.userdb.users.delete_one({ 'username': self.username })
    self.rundb.userdb.user_cache.delete_one({ 'username': self.username })
    self.rundb.userdb.flag_cache.delete_one({ 'ip': self.remote_addr })
    self.rundb.stop()
    self.rundb.runs.drop()


  def build_json_request(self, json_body):
    return DummyRequest(
      rundb=self.rundb,
      userdb=self.rundb.userdb,
      actiondb=self.rundb.actiondb,
      remote_addr=self.remote_addr,
      json_body=json_body
    )

  def invalid_password_request(self):
    return self.build_json_request({
      'username': self.username,
      'password': 'wrong password'
    })

  def correct_password_request(self, json_body={}):
    return self.build_json_request({
      'username': self.username,
      'password': self.password,
      **json_body,
    })


  def test_get_active_runs(self):
    request = DummyRequest(rundb=self.rundb)
    response = ApiView(request).active_runs()
    self.assertTrue(self.run_id in response)


  def test_get_run(self):
    request = DummyRequest(
      rundb=self.rundb,
      matchdict={'id': self.run_id}
    )
    response = ApiView(request).get_run()
    self.assertEqual(self.run_id, response['_id'])


  def test_get_elo(self):
    request = DummyRequest(
      rundb=self.rundb,
      matchdict={'id': self.run_id}
    )
    response = ApiView(request).get_elo()
    self.assertTrue(not response)


  def test_request_task(self):
    with self.assertRaises(HTTPUnauthorized):
      response = ApiView(self.invalid_password_request()).update_task()
      self.assertTrue('error' in response)

    run = self.rundb.get_run(self.run_id)
    self.assertEqual(run.get('cores'), None)

    run['tasks'][self.task_id] = {
      'num_games': 250,
      'pending': True,
      'active': False
    }
    self.rundb.buffer(run, True)

    request = self.correct_password_request({ 'worker_info': self.worker_info })
    response = ApiView(request).request_task()
    self.assertEqual(self.run_id, response['run']['_id'])
    self.assertEqual(self.task_id, response['task_id'])

    run = self.rundb.get_run(self.run_id)
    self.assertEqual(run['cores'], self.concurrency)
    task = run['tasks'][self.task_id]
    self.assertTrue(task['pending'])
    self.assertTrue(task['active'])


  def test_update_task(self):
    self.assertFalse(self.rundb.get_run(self.run_id)['results_stale'])

    with self.assertRaises(HTTPUnauthorized):
      response = ApiView(self.invalid_password_request()).update_task()
      self.assertTrue('error' in response)

    run = self.rundb.get_run(self.run_id)
    run['tasks'][self.task_id] = {
      'num_games': 250,
      'pending': True,
      'active': False
    }
    if run['args'].get('spsa'):
      del run['args']['spsa']
    self.rundb.buffer(run, True)
    request = self.correct_password_request({ 'worker_info': self.worker_info })
    ApiView(request).request_task()

    request = self.correct_password_request({
      'worker_info': self.worker_info,
      'run_id': self.run_id,
      'task_id': self.task_id,
      'stats': { 'wins': 1, 'draws': 0, 'losses': 0 }
    })

    run = self.rundb.get_run(self.run_id)
    run['tasks'][self.task_id]['pending'] = True
    run['tasks'][self.task_id]['active'] = True
    self.rundb.buffer(run, True)

    response = ApiView(request).update_task()
    self.assertTrue(response['task_alive'])
    self.assertTrue(self.rundb.get_run(self.run_id)['results_stale'])

    request.json_body['stats'] = { 'wins': 120, 'draws': 100, 'losses': 0 }
    response = ApiView(request).update_task()
    self.assertTrue(response['task_alive'])
    self.assertTrue(self.rundb.get_run(self.run_id)['results_stale'])

    task_num_games = run['tasks'][self.task_id]['num_games']
    request.json_body['stats'] = { 'wins': task_num_games, 'draws': 0, 'losses': 0 }
    response = ApiView(request).update_task()
    self.assertTrue(self.rundb.get_run(self.run_id)['results_stale'])
    self.assertFalse(response['task_alive'])


  def test_failed_task(self):
    request = self.correct_password_request({
      'run_id': self.run_id,
      'task_id': 0,
    })
    response = ApiView(request).failed_task()
    self.assertFalse(response['task_alive'])

    run = self.rundb.get_run(self.run_id)
    run['tasks'][self.task_id]['active'] = True
    run['tasks'][self.task_id]['worker_info'] = self.worker_info
    self.rundb.buffer(run, True)
    run = self.rundb.get_run(self.run_id)
    self.assertTrue(run['tasks'][self.task_id]['active'])

    request = self.correct_password_request({
      'run_id': self.run_id,
      'task_id': self.task_id,
    })
    response = ApiView(request).failed_task()
    self.assertTrue(not response)
    self.assertFalse(run['tasks'][self.task_id]['active'])


  def test_stop_run(self):
    with self.assertRaises(HTTPUnauthorized):
      response = ApiView(self.invalid_password_request()).stop_run()
      self.assertTrue('error' in response)

    run = self.rundb.get_run(self.run_id)
    self.assertFalse(run['finished'])

    request = self.correct_password_request({ 'run_id': self.run_id })
    response = ApiView(request).stop_run()
    self.assertTrue(not response)

    self.rundb.userdb.user_cache.update_one({ 'username': self.username }, {
      '$set': {
        'cpu_hours': 10000
      }
    })
    user = self.rundb.userdb.user_cache.find_one({ 'username': self.username })
    self.assertTrue(user['cpu_hours'] == 10000)

    response = ApiView(request).stop_run()
    self.assertTrue(not response)

    run = self.rundb.get_run(self.run_id)
    self.assertTrue(run['finished'])
    self.assertEqual(run['stop_reason'], 'API request')

    run['finished'] = False
    self.rundb.buffer(run, True)


  def test_upload_pgn(self):
    pgn_text = '1. e4 e5 2. d4 d5'
    request = self.correct_password_request({
      'run_id': self.run_id,
      'task_id': self.task_id,
      'pgn': base64.b64encode(zlib.compress(pgn_text.encode('utf-8'))).decode()
    })
    response = ApiView(request).upload_pgn()
    self.assertTrue(not response)

    pgn_filename_prefix = '{}-{}'.format(self.run_id, self.task_id)
    pgn = self.rundb.get_pgn(pgn_filename_prefix)
    self.assertEqual(pgn, pgn_text)
    self.rundb.pgndb.delete_one({ 'run_id': pgn_filename_prefix })


  def test_request_spsa(self):
    request = self.correct_password_request({
      'run_id': self.run_id,
      'task_id': 0,
    })
    response = ApiView(request).request_spsa()
    self.assertFalse(response['task_alive'])

    run = self.rundb.get_run(self.run_id)
    run['args']['spsa'] = {
      'iter': 1,
      'alpha': 1,
      'gamma': 1,
      'A': 1,
      'params': [{
        'name': 'param name',
        'a': 1,
        'c': 1,
        'theta': 1,
        'min': 0,
        'max': 100,
      }]
    }
    run['tasks'][self.task_id]['pending'] = True
    run['tasks'][self.task_id]['active'] = True
    self.rundb.buffer(run, True)
    request = self.correct_password_request({
      'run_id': self.run_id,
      'task_id': self.task_id,
    })
    response = ApiView(request).request_spsa()
    self.assertTrue(response['task_alive'])
    self.assertTrue(response['w_params'] is not None)
    self.assertTrue(response['b_params'] is not None)


  def test_request_version(self):
    with self.assertRaises(HTTPUnauthorized):
      response = ApiView(self.invalid_password_request()).request_version()
      self.assertTrue('error' in response)

    response = ApiView(self.correct_password_request()).request_version()
    self.assertEqual(WORKER_VERSION, response['version'])


if __name__ == '__main__':
  unittest.main()
