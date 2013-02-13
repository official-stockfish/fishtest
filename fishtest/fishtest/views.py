import os
import sys
import ujson
from pyramid.view import view_config
from pyramid.httpexceptions import HTTPFound
from urllib2 import urlopen, HTTPError

# For tasks
sys.path.append(os.path.expanduser('~/fishtest'))
from tasks.games import run_games
from tasks.celery import celery

FLOWER_URL = 'http://localhost:5555'

@view_config(route_name='home', renderer='mainpage.mak')
def mainpage(request):
  return {'project': 'fishtest'}

@view_config(route_name='tests_run', renderer='tests_run.mak')
def tests_run(request):
  if 'base-branch' in request.POST:
    run_games.delay(base_branch=request.POST['base-branch'],
                    new_branch=request.POST['test-branch'],
                    num_games=request.POST['num-games'],
                    tc=request.POST['tc'])
    request.session.flash('Started test run!')
    return HTTPFound(location=request.route_url('tests'))
  return {}

def get_celery_stats():
  machines = {}
  waiting = []

  try:
    workers = ujson.loads(urlopen(FLOWER_URL + '/api/workers').read())
    tasks = ujson.loads(urlopen(FLOWER_URL + '/api/tasks').read())

    for worker, info in workers.iteritems():
      if not info['status']:
        continue
      machine_tasks = []
      for task in info['running_tasks']:
        if task['id'] in tasks and tasks[task['id']]['state'] == 'REVOKED':
          continue

        job_result = celery.AsyncResult(task['id'])
        status = {'status': job_result.status}
        if job_result.result != None:
          status['result'] = job_result.result

        machine_tasks.append({
          'name': '---',
          'url': '',
          'status': status
        })

      machines[worker] = machine_tasks
  except HTTPError as e:
    pass

  return (machines, tasks)

@view_config(route_name='tests', renderer='tests.mak')
def tests(request):
  machines, tasks = get_celery_stats()
  waiting = []
  failed = []
  for task, info in tasks.iteritems():
    if info['state'] == 'PENDING':
      waiting.append('---')
    elif info['state'] == 'FAILURE' and info['kwargs'] != None:
      failed.append('---')

  return {
    'machines': machines,
    'waiting': waiting,
    'failed': failed,
  }
