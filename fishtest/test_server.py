import unittest
import datetime

from fishtest.rundb import RunDb

rundb = None
run_id = None
  
class CreateServerTest(unittest.TestCase):

  def tearDown(self):
    # Shutdown flush thread:
    rundb.stop()

  def test_10_create_run(self):
    global rundb, run_id
    rundb= RunDb()
    run_id = rundb.new_run('master', 'master', 100000, '10+0.01', 'book', 10, 1, '', '',
                           username='travis', tests_repo='travis', start_time= datetime.datetime.utcnow())
    print(' '); print(run_id)
    run = rundb.get_run(run_id)
    print(run['tasks'][0])
    self.assertFalse(run['tasks'][0][u'active'])
    run['tasks'][0][u'active'] = True
    
  def test_20_update_task(self):
    r= rundb.update_task(run_id, 0, {'wins': 1, 'losses': 1, 'draws': 997, 'crashes': 0, 'time_losses': 0}, 1000000, '')
    self.assertEqual(r, {'task_alive': True})
    r= rundb.update_task(run_id, 0, {'wins': 1, 'losses': 1, 'draws': 998, 'crashes': 0, 'time_losses': 0}, 1000000, '')
    self.assertEqual(r, {'task_alive': False})

  def test_30_delete_run(self):
    run = rundb.get_run(run_id)
    run['deleted'] = True
    run['finished'] = True
    for w in run['tasks']:
      w['pending'] = False
    rundb.buffer(run, True)


if __name__ == "__main__":
  unittest.main()
