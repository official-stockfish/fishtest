import os
import requests
import zipfile
import shutil
import subprocess
import sys
import time
from optparse import OptionParser
from zipfile import ZipFile
from rundb import RunDb

FISHCOOKING_URL = 'https://api.github.com/repos/mcostalba/FishCooking'

LINUX32 = {
  'system': 'linux',
  'architecture': '32',
  'make_cmd': 'make build ARCH=x86-32 COMP=gcc',
  'gcc_alias': '',
}
LINUX64 = {
  'system': 'linux',
  'architecture': '64',
  'make_cmd': 'make build ARCH=x86-64-modern COMP=gcc',
  'gcc_alias': '',
}
WIN32 = {
  'system': 'windows',
  'architecture': '32',
  'make_cmd': 'make build ARCH=x86-32 COMP=gcc',
  'gcc_alias': 'x86_64-w64-mingw32-c++',
}
WIN64 = {
  'system': 'windows',
  'architecture': '64',
  'make_cmd': 'make build ARCH=x86-64-modern COMP=gcc',
  'gcc_alias': 'x86_64-w64-mingw32-c++',
}

TARGETS = [LINUX32, LINUX64, WIN32, WIN64]

def make(orig_src_dir, destination, target):
  """Build sources in a temporary directory then move exe to destination"""
  cur_dir = os.getcwd()
  tmp_dir = tempfile.mkdtemp()
  src_dir = os.path.join(tmp_dir, '/src/')

  shutil.copytree(orig_src_dir, src_dir)
  os.chdir(src_dir)

  # Patch the makefile to cross-compile for Windows
  if len(target['gcc_alias']) > 0:
    with open('tmp', 'wt') as out:
      for line in open('Makefile'):
        out.write(line.replace('CXX=g++', 'CXX=' + target['gcc_alias']))
      shutil.copyfile('tmp', 'Makefile')

  subprocess.check_call(target['make_cmd'], shell=True)
  subprocess.check_call('make strip', shell=True)

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

def build(sha, binaries_dir):
  """Download and build to multi target a single commit"""
  print 'Downloading %s ...' % (sha)
  tmp_dir = tempfile.mkdtemp()
  src_dir = download(sha, tmp_dir)

  for t in TARGETS:
    signature = sha + '_' + t['system'] + '_' + t['architecture']
    destination = os.path.join(binaries_dir, signature)
    print 'Building %s ...' % (signature)
    make(src_dir, destination, t)

  shutil.rmtree(tmp_dir)

def binary_exists(sha, binaries_dir):
  for files in os.listdir(binaries_dir):
    if files.startswith(sha):
      return True
  else:
    return False

def survey(rundb, binaries_dir):
  sha_fields = ['resolved_base', 'resolved_new']
  runs = rundb.get_runs_to_build()
  for run in runs:
    for item in sha_fields:
        sha = run['args'][item]
        # Check before to rebuild, master could be already exsisting
        if not binary_exists(sha, binaries_dir):
            build(sha, binaries_dir)

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
    print 'Checking for runs to build...'
    survey(rundb, binaries_dir)
    time.sleep(60)

if __name__ == '__main__':
  main()
