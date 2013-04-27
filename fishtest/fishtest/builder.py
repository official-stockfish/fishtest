#!/usr/bin/python

import os
import requests
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from optparse import OptionParser
from zipfile import ZipFile
from rundb import RunDb

FISHCOOKING_URL = 'https://github.com/mcostalba/FishCooking'

LINUX32 = {
  'system': 'linux',
  'architecture': '32',
  'make_cmd': 'make build ARCH=x86-32 COMP=gcc',
  'gcc_alias': '',
  'native': True,
}
LINUX64 = {
  'system': 'linux',
  'architecture': '64',
  'make_cmd': 'make build ARCH=x86-64-modern COMP=gcc',
  'gcc_alias': '',
  'native': True,
}
WIN32 = {
  'system': 'windows',
  'architecture': '32',
  'make_cmd': 'make build ARCH=x86-32 COMP=gcc',
  'gcc_alias': 'x86_64-w64-mingw32-c++',
  'native': False,
}
WIN64 = {
  'system': 'windows',
  'architecture': '64',
  'make_cmd': 'make build ARCH=x86-64-modern COMP=gcc',
  'gcc_alias': 'x86_64-w64-mingw32-c++',
  'native': False,
}

TARGETS = [WIN32, WIN64]

def github_api(repo):
  """ Convert from https://github.com/<user>/<repo>
      To https://api.github.com/repos/<user>/<repo> """
  return repo.replace('https://github.com', 'https://api.github.com/repos')

def make(orig_src_dir, destination, target):
  """Build sources in a temporary directory then move exe to destination"""
  print 'Building %s ...' % (os.path.basename(destination))
  cur_dir = os.getcwd()
  tmp_dir = tempfile.mkdtemp()
  src_dir = os.path.join(tmp_dir, 'src')

  shutil.copytree(orig_src_dir, src_dir)
  os.chdir(src_dir)

  # Patch the makefile to cross-compile for Windows
  if len(target['gcc_alias']) > 0:
    with open('tmp', 'w') as out:
      with open('Makefile') as f:
        out.write(f.read().replace('CXX=g++', 'CXX=' + target['gcc_alias']))
    shutil.copyfile('tmp', 'Makefile')

  subprocess.check_call(target['make_cmd'], shell=True)
  subprocess.check_call('make strip', shell=True)

  shutil.move('stockfish', destination)
  os.chdir(cur_dir)
  shutil.rmtree(tmp_dir)

def download(repo_url, sha, working_dir):
  """Download and extract sources and return src directory"""
  print 'Downloading %s ...' % (sha)
  sf_zip = os.path.join(working_dir, 'sf.gz')
  with open(sf_zip, 'wb+') as f:
    f.write(requests.get(github_api(repo_url) + '/zipball/' + sha).content)
  zip_file = ZipFile(sf_zip)
  zip_file.extractall(working_dir)
  zip_file.close()

  for name in zip_file.namelist():
    if name.endswith('/src/'):
      src_dir = name
      break

  return os.path.join(working_dir, src_dir)

def get_binary_filename(sha, system, architecture):
  return sha + '_' + system + '_' + architecture

def build(repo_url, sha, binaries_dir):
  """Download and build to multi target a single commit"""
  tmp_dir = tempfile.mkdtemp()
  src_dir = download(repo_url, sha, tmp_dir)

  for t in TARGETS:
    filename = get_binary_filename(sha, t['system'], t['architecture'])
    destination = os.path.join(binaries_dir, filename)
    make(src_dir, destination, t)

  shutil.rmtree(tmp_dir)

def binary_exists(sha, binaries_dir):
  for files in os.listdir(binaries_dir):
    if files.startswith(sha):
      return True
  else:
    return False

def get_binary_url(binaries_dir, sha, worker_info):
  system = worker_info['uname'][0].lower()
  architecture = worker_info['architecture']
  architecture = '64' if '64' in architecture else '32'
  filename = get_binary_filename(sha, system, architecture)
  engine_path = os.path.join(binaries_dir, filename)
  return engine_path if os.path.exists(engine_path) else ''

def survey(rundb, binaries_dir):
  print 'Checking for runs to build...'
  items = ['resolved_base', 'resolved_new']
  runs = rundb.get_runs_to_build()
  for run in runs:
    repo_url = run['args'].get('tests_repo', FISHCOOKING_URL)
    for item in items:
      sha = run['args'][item]
      # Check before to rebuild, master could be already exsisting
      if not binary_exists(sha, binaries_dir):
        build(repo_url, sha, binaries_dir)

    # Reload run in case has been updated while compiling
    r = rundb.get_run(str(run['_id']))
    r['binaries_dir'] = binaries_dir
    rundb.runs.save(r)

def main():
  parser = OptionParser()
  (options, args) = parser.parse_args()
  if len(args) != 1:
    sys.stderr.write('Usage: %s [binaries dir]\n' % (sys.argv[0]))
    sys.exit(1)

  binaries_dir = args[0]
  if not os.path.isdir(binaries_dir):
    sys.stderr.write('Directory %s does not exist\n' % (binaries_dir))
    sys.exit(1)

  rundb = RunDb()
  while 1:
    survey(rundb, binaries_dir)
    time.sleep(60)

if __name__ == '__main__':
  main()
