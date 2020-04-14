import datetime
import json
import unittest
import base64
import zlib

from pyramid import testing

import fishtest.api
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
        run['tasks'][i]["pending"] = False

    self.rundb.buffer(run, True)

    # Set up an API user (a worker)
    self.username = 'JoeUser2'
    self.password = 'secret'
    self.remote_addr = "127.0.0.1"

    self.rundb.userdb.create_user(self.username, self.password, 'email@email.email')
    user = self.rundb.userdb.get_user(self.username)
    user['blocked'] = False
    self.rundb.userdb.save_user(user)
    self.rundb.userdb.flag_cache.insert_one({
      'ip': self.remote_addr,
      'country_code': '??'
    })

  @classmethod
  def tearDownClass(self):
    self.rundb.runs.delete_one({ '_id': self.run_id })
    self.rundb.userdb.users.delete_one({ 'username': self.username })
    self.rundb.userdb.flag_cache.delete_one({'ip': self.remote_addr })
    self.rundb.stop()


  def test_get_active_runs(self):
    request = testing.DummyRequest(rundb=self.rundb)
    response = json.loads(fishtest.api.active_runs(request))
    self.assertTrue(self.run_id in response)

  def test_get_run(self):
    request = testing.DummyRequest(
      rundb=self.rundb,
      matchdict={"id": self.run_id}
    )
    response = json.loads(fishtest.api.get_run(request))
    self.assertEqual(self.run_id, response["_id"])

  def test_get_elo(self):
    request = testing.DummyRequest(
      rundb=self.rundb,
      matchdict={"id": self.run_id}
    )
    response = json.loads(fishtest.api.get_elo(request))
    self.assertTrue(not response)

  def test_stop_run(self):
    request = testing.DummyRequest(
      rundb=self.rundb,
      userdb=self.rundb.userdb,
      json_body={"username": self.username, "password": self.password}
    )
    response = fishtest.api.stop_run(request)
    self.assertTrue(not response)

  def test_request_task(self):
    request = testing.DummyRequest(
      rundb=self.rundb,
      userdb=self.rundb.userdb,
      remote_addr=self.remote_addr,
      json_body={
        "username": self.username,
        "password": self.password,
        "worker_info": {
          "remote_addr": self.remote_addr,
          "username": self.username,
          "concurrency": 2,
          "version": fishtest.api.WORKER_VERSION
        }
      }
    )
    response = json.loads(fishtest.api.request_task(request))
    self.assertEqual(self.run_id, response["run"]["_id"])
    self.assertEqual(self.task_id, response["task_id"])

  def test_update_task(self):
    request = testing.DummyRequest(
      rundb=self.rundb,
      userdb=self.rundb.userdb,
      remote_addr=self.remote_addr,
      json_body={
        "username": self.username,
        "password": self.password,
        "worker_info": {
          "remote_addr": self.remote_addr,
          "username": self.username,
          "concurrency": 2,
          "version": fishtest.api.WORKER_VERSION
        },
        "run_id": self.run_id,
        "task_id": self.task_id,
        "stats": { "wins": 1, "draws": 0, "losses": 0 }
      }
    )
    self.assertFalse(self.rundb.get_run(self.run_id)["results_stale"])
    response = json.loads(fishtest.api.update_task(request))
    self.assertTrue(response["task_alive"])
    self.assertTrue(self.rundb.get_run(self.run_id)["results_stale"])

    request.json_body["stats"] = { "wins": 120, "draws": 100, "losses": 0 }
    response = json.loads(fishtest.api.update_task(request))
    self.assertTrue(response["task_alive"])

    request.json_body["stats"] = { "wins": 120, "draws": 100, "losses": 30 }
    response = json.loads(fishtest.api.update_task(request))
    self.assertFalse(response["task_alive"])

  def test_failed_task(self):
    request = testing.DummyRequest(
      rundb=self.rundb,
      userdb=self.rundb.userdb,
      remote_addr=self.remote_addr,
      json_body={
        "username": self.username,
        "password": self.password,
        "run_id": self.run_id,
        "task_id": 0,
      }
    )
    response = json.loads(fishtest.api.failed_task(request))
    self.assertFalse(response["task_alive"])

  def test_upload_pgn(self):
    request = testing.DummyRequest(
      rundb=self.rundb,
      userdb=self.rundb.userdb,
      remote_addr=self.remote_addr,
      json_body={
        "username": self.username,
        "password": self.password,
        "run_id": self.run_id,
        "task_id": 0,
        "pgn": base64.b64encode(zlib.compress("1. e4".encode('utf-8'))).decode()
      }
    )
    response = json.loads(fishtest.api.upload_pgn(request))
    self.assertTrue(not response)

  def test_request_spsa(self):
    request = testing.DummyRequest(
      rundb=self.rundb,
      userdb=self.rundb.userdb,
      json_body={
        "username": self.username,
        "password": self.password,
        "run_id": self.run_id,
        "task_id": 0,
      }
    )
    response = json.loads(fishtest.api.request_spsa(request))
    self.assertFalse(response["task_alive"])

  def test_request_version(self):
    request = testing.DummyRequest(
      rundb=self.rundb,
      userdb=self.rundb.userdb,
      json_body={"username": self.username, "password": "wrong"}
    )
    response = json.loads(fishtest.api.request_version(request))
    self.assertTrue('error' in response)
    request.json_body={"username": self.username, "password": self.password}
    response = json.loads(fishtest.api.request_version(request))
    self.assertEqual(fishtest.api.WORKER_VERSION, response["version"])


if __name__ == "__main__":
  unittest.main()
