def tests_repo(run):
  return run['args'].get('tests_repo', 'https://github.com/official-stockfish/Stockfish')

def diff_url(run):
  return "{}/compare/{}...{}".format(
    tests_repo(run),
    run['args']['resolved_base'][:7],
    run['args']['resolved_new'][:7]
  )