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

def main():
  parser = OptionParser()
  parser.add_option('-n', '--host', dest='host', default='54.235.120.254')
  parser.add_option('-p', '--port', dest='port', default='80')
  (options, args) = parser.parse_args()

  if len(args) != 4:
    sys.stderr.write('Usage: %s [binaries dir] [binaries url] [username] [password]\n' % (sys.argv[0]))
    sys.exit(1)

  binaries_dir = args[0]
  binaries_url = args[1]

  if not os.path.isdir(binaries_dir):
    sys.stderr.write('Directory %s does not exist\n' % (binaries_dir))
    sys.exit(1)

  worker_info = {
    'uname': platform.uname(),
    'architecture': platform.architecture(),
    'username': args[2],
    'version': '1',
  }

  payload = {
    'worker_info': worker_info,
    'password': args[3],
    'run_id': '',
    'new_engine_url': '',
    'base_engine_url':'',
  }

  system = worker_info['uname'][0].lower()
  architecture = worker_info['architecture']
  architecture = '64' if '64' in architecture else '32'

  print 'Connecting to %s...' % (remote)
  remote = 'http://%s:%s' % (options.host, options.port)

  while 1:
    try:
      print 'Fetching build...'
      run = requests.post(remote + '/api/request_build', data=json.dumps(payload))
      run = json.loads(run.text)

      if 'args' in run:
        filenames = []
        repo_url = run['args']['tests_repo']
        for item in ['resolved_new', 'resolved_base']:
          sha = run['args'][item]
          filenames.append(get_binary_filename(sha, system, architecture))
          if not binary_exists(sha, binaries_dir):
            build(repo_url, sha, binaries_dir)

        payload['run_id'] = run['run_id']
        payload['new_engine_url'] = binaries_url + '/' + filenames[0]
        payload['base_engine_url'] = binaries_url + '/' + filenames[1]
        req = requests.post(remote + '/api/build_ready', data=json.dumps(payload))
        continue

    except:
      sys.stderr.write('Exception accessing host:\n')
      traceback.print_exc()

    time.sleep(60)

if __name__ == '__main__':
  main()

