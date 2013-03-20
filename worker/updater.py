from __future__ import absolute_import

import os
import shutil
import sys
from zipfile import ZipFile
from games import robust_download

FISHTEST_URL = 'https://api.github.com/repos/glinscott/fishtest'

def restart(worker_dir):
  """Restarts the worker, using the same arguments"""
  args = sys.argv[:]
  args.insert(0, sys.executable)
  if sys.platform == 'win32':
    args = ['"%s"' % arg for arg in args]

  os.chdir(worker_dir)
  os.execv(sys.executable, args)

def update():
  worker_dir = os.path.dirname(os.path.realpath(__file__))
  update_dir = os.path.join(worker_dir, 'update')
  if not os.path.exists(update_dir):
    os.makedirs(update_dir)

  with open(os.path.join(update_dir, 'ft.zip'), 'wb+') as f:
    f.write(robust_download(FISHTEST_URL + '/zipball/master'))

  # Assumes updater.py is at root of worker directory!
  relative_worker_dir = os.path.basename(worker_dir)

  zip_file = ZipFile(os.path.join(update_dir, 'ft.zip'))
  prefix = os.path.commonprefix([n.filename for n in zip_file.infolist()])
  for name in zip_file.infolist():
    dirname = os.path.dirname(name.filename)
    if name.filename.startswith(os.path.join(prefix, relative_worker_dir)):
      #zip_file.open(name)
      print name.filename

  shutil.rmtree(update_dir)

  restart(worker_dir)
