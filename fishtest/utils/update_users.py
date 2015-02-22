#!/usr/bin/python
import datetime, os, sys

# For tasks
sys.path.append(os.path.expanduser('~/fishtest/fishtest'))
from fishtest.rundb import RunDb
from fishtest.views import parse_tc, delta_date

def update_users():
  rundb = RunDb()

  info = {}
  for u in rundb.userdb.get_users():
    username = u['username']
    info[username] = {'username': username,
                      'cpu_hours': 0,
                      'games': 0,
                      'tests': 0,
                      'tests_repo': u.get('tests_repo', ''),
                      'last_updated': datetime.datetime.min,
                      'games_per_hour': 0.0,}

  for run in rundb.get_runs():
    if 'deleted' in run:
      continue
    if 'username' in run['args']:
      username = run['args']['username']
      info[username]['tests'] += 1

    tc = parse_tc(run['args']['tc'])
    for task in run['tasks']:
      if 'worker_info' not in task:
        continue
      username = task['worker_info'].get('username', None)
      if username == None:
        continue

      if 'stats' in task:
        stats = task['stats']
        num_games = stats['wins'] + stats['losses'] + stats['draws']
      else:
        num_games = task['num_games']

      info[username]['last_updated'] = max(task['last_updated'], info[username]['last_updated'])
      info[username]['cpu_hours'] += float(num_games * tc / (60 * 60))
      info[username]['games'] += num_games

  machines = rundb.get_machines()
  for machine in machines:
    games_per_hour = (machine['nps'] / 1200000.0) * (3600.0 / parse_tc(machine['run']['args']['tc'])) * int(machine['concurrency'])
    info[machine['username']]['games_per_hour'] += games_per_hour

  users = []
  for u in info.keys():
    user = info[u]
    user['last_updated'] = delta_date(user['last_updated'])
    users.append(user)

  users = [u for u in users if u['games'] > 0 or u['tests'] > 0]

  rundb.userdb.user_cache.remove()
  rundb.userdb.user_cache.insert(users)

def main():
  update_users()

if __name__ == '__main__':
  main()
