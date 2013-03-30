from github import Github
from subprocess import call
import os.path
import requests
import zipfile
import shutil
import time
from zipfile import ZipFile

#Parameters
g = Github("GITHUBLOGIN", "GITHUBPASSWORD")
binaryPath="/home/ec2-user/autobuilder/binary/"
sourcePath="/home/ec2-user/autobuilder/src/"
repo=g.get_repo("mcostalba/Stockfish")

FISHCOOKING_URL = 'https://api.github.com/repos/mcostalba/FishCooking'

def build(orig_src_dir, destination, make_cmd):
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

def survey():
    for commit in repo.get_commits()[:20]:
        print commit.sha
        if not (os.path.isfile(binaryPath+"stockfish-"+commit.sha+".exe")):
            build(commit.sha)

while 1:
    survey()
    time.sleep(60)
