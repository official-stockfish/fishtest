from __future__ import absolute_import

import os
import requests
import shutil
import sys
from zipfile import ZipFile
from distutils.dir_util import copy_tree

WORKER_URL = 'https://github.com/glinscott/fishtest/archive/worker.zip'

def restart(worker_dir):
  """Restarts the worker, using the same arguments"""
  args = sys.argv[:]
  args.insert(0, sys.executable)
  if sys.platform == 'win32':
    args = ['"%s"' % arg for arg in args]

  os.chdir(worker_dir)
  os.execv(sys.executable, args) # This does not return !

def update():
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
  worker_src = os.path.join(update_dir, prefix, 'worker')
  copy_tree(worker_src, worker_dir)
  shutil.rmtree(update_dir)

  restart(worker_dir)
