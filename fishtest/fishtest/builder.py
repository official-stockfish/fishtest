import os
import requests
import zipfile
import shutil
import subprocess
import time
from zipfile import ZipFile
from rundb import RunDb

FISHCOOKING_URL = 'https://api.github.com/repos/mcostalba/FishCooking'
BINARIES_DIR_PATH = 'binaries'
WIN32 = {
  'system': 'windows',
  'architecture': '32',
  'make_cmd': 'make build ARCH=x86-32 COMP=gcc',
}
WIN64 = {
  'system': 'windows',
  'architecture': '64',
  'make_cmd': 'make build ARCH=x86-64-modern COMP=gcc',
}

TARGETS = [WIN32, WIN64]

def make(orig_src_dir, destination, make_cmd):
  """Build sources in a temporary directory then move exe to destination"""
  cur_dir = os.getcwd()
  tmp_dir = tempfile.mkdtemp()
  src_dir = os.path.join(tmp_dir, '/src/')

  shutil.copytree(orig_src_dir, src_dir)
  os.chdir(src_dir)

  # Patch the makefile to cross-compile
  with open('tmp', 'wt') as out:
    for line in open('Makefile'):
      out.write(line.replace('CXX=g++', 'CXX=x86_64-w64-mingw32-c++'))
    shutil.copyfile('tmp', 'Makefile')

  subprocess.check_call(make_cmd, shell=True)

  shutil.move('stockfish', destination)
  os.chdir(cur_dir)
  shutil.rmtree(tmp_dir)

def download(sha, working_dir):
  """Download and extract sources and return src directory"""
  sf_zip = os.path.join(working_dir, 'sf.gz')
  with open(sf_zip, 'wb+') as f:
    f.write(requests.get(FISHCOOKING_URL + '/zipball/' + sha).content)
  zip_file = ZipFile(sf_zip)
  zip_file.extractall()
  zip_file.close()

  for name in zip_file.namelist():
    if name.endswith('/src/'):
      src_dir = name
      break

  return os.path.join(working_dir, src_dir)

def build(sha, binaries_dir, targets):
  """Download and build to multi target a single commit"""
  tmp_dir = tempfile.mkdtemp()
  src_dir = download(sha, tmp_dir)

  for t in TARGETS:
    signature = t['system'] + t['architecture'] + '_' + sha
    destination = os.path.join(binaries_dir, signature)
    make(src_dir, destination, t['make_cmd'])

  shutil.rmtree(tmp_dir)

def binary_exsists(sha, binaries_dir):
  for files in os.listdir(binaries_dir):
    if files.endswith(sha):
      return True
  else:
    return False

def survey(rundb):
  sha_fields = ['resolved_base', 'resolved_new']
  runs = rundb.get_runs()
  for run in runs:
    if 'binaries_dir' not in run:
      continue
    if len(run['binaries_dir']) > 0:
      continue
    for item in sha_fields:
        sha = run['args'][item]
        # Check before to rebuild, master could be already exsisting
        if not binary_exsists(sha, BINARIES_DIR_PATH):
            build(sha, BINARIES_DIR_PATH)

    # Reload run in case has been updated while compiling
    r = rundb.get_run(str(run['_id']))
    r['binaries_dir'] = BINARIES_DIR_PATH
    rundb.runs.save(r)

def main():
  rundb = RunDb()
  while 1:
    survey(rundb)
    time.sleep(60)

if __name__ == '__main__':
  main()
