#!/usr/bin/python
import os, sys

# For tasks
sys.path.append(os.path.expanduser('~/fishtest/fishtest'))
from fishtest.rundb import RunDb

def create_indices():
  rundb = RunDb()
  rundb.build_indices()

def main():
  create_indices()

if __name__ == '__main__':
  main()
