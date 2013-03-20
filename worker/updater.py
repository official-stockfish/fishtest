from __future__ import absolute_import

import os
import requests
import shutil
import sys
from zipfile import ZipFile

FISHTEST_URL = 'https://api.github.com/repos/glinscott/fishtest'

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

  with open(os.path.join(update_dir, 'ft.zip'), 'wb+') as f:
    f.write(requests.get(FISHTEST_URL + '/zipball/master').content)

  # Assumes updater.py is at root of worker directory!
  relative_worker_dir = os.path.basename(worker_dir)

  zip_file = ZipFile(os.path.join(update_dir, 'ft.zip'))
  prefix = os.path.commonprefix([n.filename for n in zip_file.infolist()])
  for name in zip_file.infolist():
    dirname = os.path.dirname(name.filename)
    file_prefix = os.path.join(prefix, relative_worker_dir)
    if name.filename.startswith(file_prefix):
      filename = name.filename[len(file_prefix)+1:]
      if len(filename) == 0:
        continue

      print 'Updating', filename
      with open(os.path.join(worker_dir, filename), 'w') as f:
        f.write(zip_file.open(name).read())

  zip_file.close()
  shutil.rmtree(update_dir)

  restart(worker_dir)
