import unittest
import time

from fishtest.fishtest.rundb import RunDb

rundb = None
run_id = None
  
class CreateServerTest(unittest.TestCase):

  def tearDown(self):
    # Shutdown flush thread:
    rundb.timer = None
    time.sleep(2)

  def test_create_run(self):
    global rundb, run_id
    rundb= RunDb()
    run_id = rundb.new_run('master', 'master', 100000, '10+0.01', 'book', 10, 1, '', '')
    print(' '); print(run_id)
    run = rundb.get_run(run_id)
    print(run['tasks'][0])
    self.assertFalse(run['tasks'][0][u'active'])
    run['tasks'][0][u'active'] = True
    
  def test_update_task(self):
    r= rundb.update_task(run_id, 0, {'wins': 1, 'losses': 1, 'draws': 997}, 1000000, '')
    self.assertEqual(r, {'task_alive': True})
    r= rundb.update_task(run_id, 0, {'wins': 1, 'losses': 1, 'draws': 998}, 1000000, '')
    self.assertEqual(r, {'task_alive': False})


if __name__ == "__main__":
  unittest.main()
