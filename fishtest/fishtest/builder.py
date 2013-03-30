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

def verify_signature(engine, signature):
  bench_sig = ''
  print 'Verifying signature of %s ...' % (os.path.basename(engine))
  with open(os.devnull, 'wb') as f:
    p = subprocess.Popen([engine, 'bench'], stderr=subprocess.PIPE, stdout=f, universal_newlines=True)
  for line in iter(p.stderr.readline,''):
    if 'Nodes searched' in line:
      bench_sig = line.split(': ')[1].strip()

  p.wait()
  if p.returncode != 0:
    raise Exception('Bench exited with non-zero code %d' % (p.returncode))

  if int(bench_sig) != int(signature):
    raise Exception('Wrong bench in %s Expected: %s Got: %s' % (engine, signature, bench_sig))

def make(orig_src_dir, destination, target):
  """Build sources in a temporary directory then move exe to destination"""
  print 'Building %s ...' % (os.path.basename(destination))
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
  print 'Downloading %s ...' % (sha)
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

def build(sha, signature, binaries_dir):
  """Download and build to multi target a single commit"""
  tmp_dir = tempfile.mkdtemp()
  src_dir = download(sha, tmp_dir)

  for t in TARGETS:
    filename = sha + '_' + t['system'] + '_' + t['architecture']
    destination = os.path.join(binaries_dir, filename)
    make(src_dir, destination, t)
    if t['native']: # We can run only native builds
      verify_signature(destination, signature)

  shutil.rmtree(tmp_dir)

def binary_exists(sha, binaries_dir):
  for files in os.listdir(binaries_dir):
    if files.startswith(sha):
      return True
  else:
    return False

def survey(rundb, binaries_dir):
  print 'Checking for runs to build...'
  items = [('resolved_base', 'base_signature'), ('resolved_new', 'new_signature')]
  runs = rundb.get_runs_to_build()
  for run in runs:
    for item in items:
        sha, signature = run['args'][item[0]], run['args'][item[1]]
        # Check before to rebuild, master could be already exsisting
        if not binary_exists(sha, binaries_dir):
            build(sha, signature, binaries_dir)

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
