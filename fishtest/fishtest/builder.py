from github import Github
from subprocess import call
import os.path
import urllib
import zipfile
import shutil
import time

#Parameters
g = Github("GITHUBLOGIN", "GITHUBPASSWORD")
binaryPath="/home/ec2-user/autobuilder/binary/"
sourcePath="/home/ec2-user/autobuilder/src/"
repo=g.get_repo("mcostalba/Stockfish")

#To launch web server in the binary directory, type : python -c "import SimpleHTTPServer;SimpleHTTPServer.test()"

def build(sha):
    #Get the sources
    urllib.urlretrieve ("https://github.com/mcostalba/Stockfish/archive/"+sha+".zip",sourcePath+sha+"-src.zip")
    zfile = zipfile.ZipFile(sourcePath+sha+"-src.zip")
    zfile.extractall(sourcePath)
    zfile.close()
    os.remove(sourcePath+sha+"-src.zip")
    #Build the sources
    os.chdir(sourcePath+"Stockfish-"+sha+"/src")
    #Patch the makefile
    with open("Makefile-x86_64-w64-mingw32", "wt") as out:
        for line in open("Makefile"):
            out.write(line.replace("CXX=g++", "CXX=x86_64-w64-mingw32-c++"))
    shutil.copyfile("Makefile-x86_64-w64-mingw32","Makefile")
    #Launch make
    call(["make","build","ARCH=x86-64-modern"])
    shutil.copyfile("stockfish",binaryPath+"stockfish-"+sha+".exe")


def survey():
    for commit in repo.get_commits()[:20]:
        print commit.sha
        if not (os.path.isfile(binaryPath+"stockfish-"+commit.sha+".exe")):
            build(commit.sha)

while 1:
    survey()
    time.sleep(60)
