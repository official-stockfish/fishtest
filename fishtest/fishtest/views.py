import datetime
import transaction
import os
import persistent, persistent.dict, persistent.list
import sys
import ujson
from pyramid.view import view_config
from pyramid.httpexceptions import HTTPFound
from urllib2 import urlopen, HTTPError
from ZODB.FileStorage import FileStorage
from ZODB.DB import DB

# For tasks
sys.path.append(os.path.expanduser('~/fishtest'))
from tasks.games import run_games
from tasks.celery import celery

FLOWER_URL = 'http://localhost:5555'

def get_db():
  storage = FileStorage(os.path.expanduser('~/testruns.db'))
  db = DB(storage)
  connection = db.open()
  return connection.root()

def get_tasks_db():
  db = get_db()
  if 'tasks' not in db:
    db['tasks'] = persistent.dict.PersistentDict()
  return db['tasks']

@view_config(route_name='home', renderer='mainpage.mak')
def mainpage(request):
  return {'project': 'fishtest'}

@view_config(route_name='tests_run', renderer='tests_run.mak')
def tests_run(request):
  if 'base-branch' in request.POST:
    args = {
      'base_branch': request.POST['base-branch'],
      'new_branch': request.POST['test-branch'],
      'num_games': request.POST['num-games'],
      'tc': request.POST['tc'],
    }
    new_task = run_games.delay(**args)

    tasks_db = get_tasks_db()
    tasks_db[new_task.id] = {'args': args,
                             'start_time': datetime.datetime.now() }
    transaction.get().commit()

    request.session.flash('Started test run!')
    return HTTPFound(location=request.route_url('tests'))
  return {}

def get_celery_stats(tasks_db):
  machines = {}
  waiting = []

  try:
    workers = ujson.loads(urlopen(FLOWER_URL + '/api/workers').read())
    tasks = ujson.loads(urlopen(FLOWER_URL + '/api/tasks').read())

    # Update task states
    for id, task in tasks.iteritems():
      if id in tasks_db:
        tasks_db[id]['raw'] = task
    transaction.get().commit()

    for worker, info in workers.iteritems():
      if not info['status']:
        continue
      machine_tasks = []
      for task in info['running_tasks']:
        if task['id'] in tasks and tasks[task['id']]['state'] == 'REVOKED':
          continue

        job_result = celery.AsyncResult(task['id'])
        # Workaround celery throwing exception accessing task status.
        status = None
        for _ in xrange(5):
          try:
            status = {'status': job_result.status}
          except:
            pass

        if status == None:
          continue
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

class TestRun(persistent.Persistent):
  def __init__(self, id):
    self.id = id
  
@view_config(route_name='tests', renderer='tests.mak')
def tests(request):
  tasks_db = get_tasks_db()

  machines, tasks = get_celery_stats(tasks_db)
  waiting = []
  failed = []
  for task, info in tasks.iteritems():
    if info['state'] == 'PENDING':
      waiting.append('---')
    elif info['state'] == 'FAILURE' and info['kwargs'] != None:
      failed.append('---')

  runs = [t for t in tasks_db.values()]
  runs = sorted(runs, key=lambda k: k['start_time'])

  return {
    'machines': machines,
    'waiting': waiting,
    'failed': failed,
    'runs': runs 
  }
