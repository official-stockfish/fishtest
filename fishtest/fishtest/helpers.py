def diff_url(run):
  return "{}/compare/{}...{}".format(
    run['args'].get('tests_repo', 'https://github.com/mcostalba/FishCooking'),
    run['args']['resolved_base'][:7],
    run['args']['resolved_new'][:7]
  )