import unittest
import worker
import os
import os.path
import subprocess

class workerTest(unittest.TestCase):

  def tearDown(self):
    if os.path.exists('foo.txt'):
      os.remove('foo.txt')
   
  def test_config_setup(self):      
    config = worker.setup_config_file('foo.txt')
        
    self.assertTrue(config.has_section('login'))
    self.assertTrue(config.has_section('parameters'))
    self.assertTrue(config.has_option('login', 'username'))
    self.assertTrue(config.has_option('login', 'password'))
    self.assertTrue(config.has_option('parameters', 'host'))
    self.assertTrue(config.has_option('parameters', 'port'))
    self.assertTrue(config.has_option('parameters', 'concurrency'))
        
  def test_worker_script(self):
    p = subprocess.Popen(["python" , "worker.py"], stderr = subprocess.PIPE)
    result = p.stderr.readline()
    self.assertEqual(result, 'worker.py [username] [password]\n')

if __name__ == "__main__":
  unittest.main()
