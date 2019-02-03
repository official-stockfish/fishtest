from __future__ import absolute_import

import os
import shutil
import sys
import requests
from zipfile import ZipFile
from distutils.dir_util import copy_tree

start_dir = os.getcwd()

WORKER_URL = 'https://github.com/glinscott/fishtest/archive/master.zip'

def do_restart():
  """Restarts the worker, using the same arguments"""
  args = sys.argv[:]
  args.insert(0, sys.executable)
  if sys.platform == 'win32':
    args = ['"%s"' % arg for arg in args]

  os.chdir(start_dir)
  os.execv(sys.executable, args) # This does not return !

def update(restart=True, test=False):
  worker_dir = os.path.dirname(os.path.realpath(__file__))
  update_dir = os.path.join(worker_dir, 'update')
  if not os.path.exists(update_dir):
    os.makedirs(update_dir)

  worker_zip = os.path.join(update_dir, 'wk.zip')
  with open(worker_zip, 'wb+') as f:
    f.write(requests.get(WORKER_URL).content)

  zip_file = ZipFile(worker_zip)
  zip_file.extractall(update_dir)
  zip_file.close()
  prefix = os.path.commonprefix([n.filename for n in zip_file.infolist()])
  fishtest_src = os.path.join(update_dir, prefix)
  fishtest_dir = os.path.dirname(worker_dir) # fishtest_dir is assumed to be parent of worker_dir
  if not test:
    copy_tree(fishtest_src, fishtest_dir)
  else:
    file_list = os.listdir(fishtest_src)
  shutil.rmtree(update_dir)

  print("start_dir: " + start_dir)
  if restart:
    do_restart()

  if test:
    return file_list

if __name__ == '__main__':
  update(False)
