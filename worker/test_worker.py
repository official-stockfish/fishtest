import unittest
import worker
import games
import os
import os.path
import subprocess
import games

class workerTest(unittest.TestCase):

  def tearDown(self):
    if os.path.exists('foo.txt'):
      os.remove('foo.txt')
    if os.path.exists('polyglot.ini'):
      os.remove('polyglot.ini')
   
   
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
    
  def test_item_download(self):
    self.assertTrue(games.cleanup('foo.txt', '.'))
    with open(os.path.join('.', 'foo.txt'), 'w'):
      pass
    self.assertFalse(games.cleanup('foo.txt', '.'))
    self.assertFalse(os.path.exists('foo.txt'))
    
    f = open(os.path.join('.', 'foo.txt'), 'w')
    f.write('This file is not empty')
    f.close()
    self.assertTrue(os.path.exists(os.path.join('.','foo.txt')))
    self.assertTrue(games.cleanup('foo.txt', '.'))
    
    games.setup('polyglot.ini', '.')
    self.assertTrue(os.path.exists(os.path.join('.','polyglot.ini')))
    
    

  def test_setup_exception(self): 
    cwd = os.getcwd()
    with self.assertRaises(Exception):
      games.setup_engine('foo', cwd, 'foo', 'https://foo', 1)

if __name__ == "__main__":
  unittest.main()
