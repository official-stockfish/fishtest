import os
import requests
import zipfile
import shutil
import subprocess
import time
from zipfile import ZipFile
from rundb import RunDb

FISHCOOKING_URL = 'https://api.github.com/repos/mcostalba/FishCooking'

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

  for t in targets:
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
        if not binary_exsists(sha, binaries_dir):
            build(sha, binaries_dir)

    # Reload run in case has been updated while compiling
    r = rundb.get_run(str(run['_id']))
    r['binaries_dir'] = binaries_dir
    rundb.runs.save(r)

def main():
  rundb = RunDb()
  while 1:
    survey(rundb)
    time.sleep(60)

if __name__ == '__main__':
  main()
