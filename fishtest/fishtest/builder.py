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

#To launch web server in the binary directory, type : python -c "import SimpleHTTPServer;SimpleHTTPServer.test()"

def build(sha, destination, make_cmd):
  """Download and build sources in a temporary directory then move exe to destination"""
  cur_dir = os.cwd()
  tmp_dir = tempfile.mkdtemp()
  os.chdir(tmp_dir)

  with open('sf.gz', 'wb+') as f:
    f.write(requests.get(FISHCOOKING_URL + '/zipball/' + sha).content)
  zip_file = ZipFile('sf.gz')
  zip_file.extractall()
  zip_file.close()

  for name in zip_file.namelist():
    if name.endswith('/src/'):
      src_dir = name

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

def survey():
    for commit in repo.get_commits()[:20]:
        print commit.sha
        if not (os.path.isfile(binaryPath+"stockfish-"+commit.sha+".exe")):
            build(commit.sha)

while 1:
    survey()
    time.sleep(60)
