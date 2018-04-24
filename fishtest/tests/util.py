from fishtest.rundb import RunDb

def find_run(arg='username', value='travis'):
  rundb= RunDb()
  for r in rundb.get_unfinished_runs():
    if r['args'][arg] == value:
      return r
  return None
