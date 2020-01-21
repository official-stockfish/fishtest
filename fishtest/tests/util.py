from fishtest.rundb import RunDb

def find_run(arg='username', value='travis'):
  rundb = RunDb()
  for run in rundb.get_unfinished_runs():
    if run['args'][arg] == value:
      return run
  return None
