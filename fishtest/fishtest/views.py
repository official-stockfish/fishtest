import os
import sys
from pyramid.view import view_config

# For tasks
sys.path.append(os.path.expanduser('~/fishtest'))
from tasks.games import run_games

@view_config(route_name='home', renderer='mainpage.mak')
def mainpage(request):
  return {'project': 'fishtest'}

@view_config(route_name='tests_run', renderer='tests_run.mak')
def tests_run(request):
  if 'base-branch' in request.POST:
    run_games.delay(base_branch=request.POST['base-branch'],
                    test_branch=request.POST['test-branch'],
                    num_games=request.POST['num-games'],
                    tc=request.POST['tc'])
    request.session.flash('Started test run!')
    return HTTPFound(location=request.route_url('tests'))
  return {}
