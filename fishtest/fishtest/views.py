import copy
import datetime
import numpy
import os
import scipy
import scipy.stats
import sys
import json
import smtplib
import requests
from email.mime.text import MIMEText
from collections import defaultdict
from pyramid.security import remember, forget, authenticated_userid, has_permission
from pyramid.view import view_config, forbidden_view_config
from pyramid.httpexceptions import HTTPFound

import stat_util

@view_config(route_name='home', renderer='mainpage.mak')
def mainpage(request):
  return HTTPFound(location=request.route_url('tests'))

@view_config(route_name='login', renderer='mainpage.mak')
@forbidden_view_config(renderer='mainpage.mak')
def login(request):
  login_url = request.route_url('login')
  referrer = request.url
  if referrer == login_url:
    referrer = '/' # never use the login form itself as came_from
  came_from = request.params.get('came_from', referrer)

  if 'form.submitted' in request.params:
    username = request.params['username']
    password = request.params['password']
    token = request.userdb.authenticate(username, password)
    if 'error' not in token:
      headers = remember(request, username)
      return HTTPFound(location=came_from, headers=headers)

    request.session.flash('Incorrect password')

  return {}

@view_config(route_name='signup', renderer='signup.mak')
def signup(request):
  if 'form.submitted' in request.params:
    if len(request.params.get('password', '')) == 0:
      request.session.flash('Non-empty password required')
      return {}

    result = request.userdb.create_user(
      username=request.params['username'],
      password=request.params['password'],
      email=request.params['email']
    )

    if not result:
      request.session.flash('Invalid username')
    else:
      return HTTPFound(location=request.route_url('login'))

  return {}

def delta_date(date):
  if date != datetime.datetime.min:
    diff = datetime.datetime.utcnow() - date
    if diff.days != 0:
      delta = '%d days ago' % (diff.days)
    elif diff.seconds / 3600 > 1:
      delta = '%d hours ago' % (diff.seconds / 3600)
    elif diff.seconds / 60 > 1:
      delta = '%d minutes ago' % (diff.seconds / 60)
    else:
      delta = 'seconds ago'
  else:
    delta = 'Never'
  return delta

def parse_tc(tc):
  # Total time for a game is assumed to be the double of tc for each player
  # reduced for 70% becuase on average game is stopped earlier. For instance
  # in case of 60+0.05 time for each player is 62 secs, so the game duration
  # is 62*2*70%
  scale = 2 * 0.90

  # Parse the time control in cutechess format
  if tc == '15+0.05':
    return 17.0 * scale

  if tc == '60+0.05':
    return 62.0 * scale

  chunks = tc.split('+')
  increment = 0.0
  if len(chunks) == 2:
    increment = float(chunks[1])

  chunks = chunks[0].split('/')
  num_moves = 0
  if len(chunks) == 2:
    num_moves = int(chunks[0])

  time_tc = chunks[-1]
  chunks = time_tc.split(':')
  if len(chunks) == 2:
    time_tc = float(chunks[0]) * 60 + float(chunks[1])
  else:
    time_tc = float(chunks[0])

  if num_moves > 0:
    time_tc = time_tc * (40.0 / num_moves)
  return (time_tc + (increment * 40.0)) * scale

@view_config(route_name='actions', renderer='actions.mak')
def actions(request):
  actions = []
  for action in request.actiondb.get_actions(100):
    item = {
      'action': action['action'],
      'time': action['time'],
      'username': action['username'],
    }
    if action['action'] == 'modify_run':
      item['run'] = action['data']['before']['args']['new_tag']
      item['_id'] = action['data']['before']['_id']
      item['description'] = []

      before = action['data']['before']['args']['priority']
      after = action['data']['after']['args']['priority']
      if before != after:
        item['description'].append('priority changed from %s to %s' % (before, after))

      before = action['data']['before']['args']['num_games']
      after = action['data']['after']['args']['num_games']
      if before != after:
        item['description'].append('games changed from %s to %s' % (before, after))

      item['description'] = 'modify: ' + ','.join(item['description'])
    else:
      item['run'] = action['data']['args']['new_tag']
      item['_id'] = action['data']['_id']
      item['description'] = ' '.join(action['action'].split('_'))
      if action['action'] == 'stop_run':
        item['description'] += ': %s' % (action['data'].get('stop_reason', 'User stop'))

    actions.append(item)

  return {'actions': actions}

@view_config(route_name='users', renderer='users.mak')
def users(request):
  users = list(request.userdb.user_cache.find())
  users.sort(key=lambda k: k['cpu_hours'], reverse=True)
  return {'users': users}

def get_sha(branch, repo_url):
  """Resolves the git branch to sha commit"""
  api_url = repo_url.replace('https://github.com', 'https://api.github.com/repos')
  commit = requests.get(api_url + '/commits/' + branch).json()
  if 'sha' in commit:
    return commit['sha'], commit['commit']['message'].split('\n')[0]
  else:
    return '', ''

@view_config(route_name='regression', renderer='regression.mak')
def regression(request):
  fishtest_regression_data = [
    {'elo': '48.16', 'error': '2.0', 'link': '54a710160ebc5962f8460cf3', 'date': u'2015-01-02T20:31:02Z', 'commit': '91cc82a'},
    {'elo': '46.26', 'error': '1.9', 'link': '549e0cfa0ebc595444a9aa4f', 'date': u'2014-12-22T07:33:07Z', 'commit': '296534f'},
    {'elo': '41.42', 'error': '1.9', 'link': '548716860ebc59615b9c1cda', 'date': u'2014-12-08T00:18:26Z', 'commit': '1588642'},
    {'elo': '39.02', 'error': '1.9', 'link': '5479f1ef0ebc5910c1f22551', 'date': u'2014-11-25T23:56:48Z', 'commit': 'fe07ae4'},
    {'elo': '36.21', 'error': '1.9', 'link': '5463d2e40ebc592ab9e50ff7', 'date': u'2014-11-10T23:06:12Z', 'commit': 'c6d45c6'},
    {'elo': '31.00', 'error': '1.9', 'link': '545559640ebc59410ea4e5fa', 'date': u'2014-11-01T21:24:33Z', 'commit': '79fa72f'},
    {'elo': '27.58', 'error': '1.9', 'link': '54411bc40ebc59731a7ea6ae', 'date': u'2014-10-15T18:36:22Z', 'commit': '480682b'},
    {'elo': '22.80', 'error': '1.9', 'link': '54276b500ebc59568afa4265', 'date': u'2014-09-27T20:33:28Z', 'commit': 'ea9c424'},
    {'elo': '15.90', 'error': '1.8', 'link': '54144bf40ebc5923f6d66d54', 'date': u'2014-09-04T19:19:03Z', 'commit': 'cd065dd'},
    {'elo': '19.68', 'error': '1.8', 'link': '53e207dd0ebc592db1a06475', 'date': u'2014-08-06T10:42:10Z', 'commit': '9da0155'},
    {'elo': '19.63', 'error': '1.8', 'link': '53cff3620ebc592c34a4a383', 'date': u'2014-07-22T23:05:10Z', 'commit': '4758fd3'},
    {'elo': '10.78', 'error': '1.8', 'link': '53b06b140ebc5948a2398082', 'date': u'2014-06-29T19:17:40Z', 'commit': 'ffedfa3'},
    {'elo': '8.30', 'error': '2.0', 'link': '539d0ccf0ebc59659be39682', 'date': u'2014-06-11T23:32:16Z', 'commit': '84dabe5'},
    {'elo': '5.35', 'error': '1.8', 'link': '538e10500ebc5940a3b7f018', 'date': u'2014-06-03T18:01:36Z', 'commit': 'adeded2'}]

  jenslehmann_regression_data = [{'description': '04-01-14 Run 3', 'games':'63180', 'data':[
    {'date_committed': u'2014-12-28T18:06:56Z', 'sha': '6933f05f4b1b7b1bd2c072029bf5a06cbeac5b0b', 'points': '32322.00', 'elo': '8.1', 'error': '2.0'}, 
    {'date_committed': u'2014-12-25T10:09:07Z', 'sha': '2bfacf136cf780936aab3ddfb1dfce0163d09d40', 'points': '32212.50', 'elo': '6.9', 'error': '2.0'}, 
    {'date_committed': u'2014-12-14T19:45:43Z', 'sha': '0edb6348d20ec35a8ac65453239097078d947b7e', 'points': '32191.00', 'elo': '6.6', 'error': '1.9'}, 
    {'date_committed': u'2014-12-13T07:22:37Z', 'sha': '14cf27e6f65787a1f9c8e4759ae0fcc218f37d2d', 'points': '32106.50', 'elo': '5.7', 'error': '2.0'}, 
    {'date_committed': u'2014-11-12T21:02:20Z', 'sha': 'b777b17f6ff7fe9670d864cf31106fdefdca3001', 'points': '32101.50', 'elo': '5.6', 'error': '1.9'}, 
    {'date_committed': u'2014-11-16T23:48:30Z', 'sha': '99f2c1a2a64cac94ee56324fa25f8fba04cd1347', 'points': '32059.00', 'elo': '5.2', 'error': '2.0'}, 
    {'date_committed': u'2014-11-18T10:57:57Z', 'sha': '4aca11ae2a37df653b54f554a3d8b3005c063447', 'points': '32022.50', 'elo': '4.8', 'error': '1.9'}, 
    {'date_committed': u'2014-11-24T00:50:36Z', 'sha': '7ad59d9ac9cbeae8b95843a720a53c99bb1f0d3b', 'points': '32014.00', 'elo': '4.7', 'error': '1.8'}, 
    {'date_committed': u'2014-11-12T21:00:16Z', 'sha': 'db4b8ee000912f88927757eb8dee255b8d66a4b4', 'points': '31953.50', 'elo': '4.0', 'error': '1.9'}, 
    {'date_committed': u'2014-11-16T23:50:33Z', 'sha': 'd65c9a326294a1f7bedf8f9a386b155f10055b42', 'points': '31945.50', 'elo': '3.9', 'error': '2.0'}, 
    {'date_committed': u'2014-12-20T17:53:44Z', 'sha': '323103826274c6ea23d36fd05ef0744f8d38cd3f', 'points': '31941.50', 'elo': '3.9', 'error': '1.8'}, 
    {'date_committed': u'2014-11-09T19:36:28Z', 'sha': '1b0df1ae141be1461e3fbe809b5b27c3e360753f', 'points': '31934.00', 'elo': '3.8', 'error': '2.0'}, 
    {'date_committed': u'2014-12-28T10:58:29Z', 'sha': 'f9571e8d57381275f08ffbfb960358319d4c34dd', 'points': '31918.50', 'elo': '3.6', 'error': '1.9'}, 
    {'date_committed': u'2014-12-07T23:58:05Z', 'sha': 'a87da2c4b3dce975fa8642c352c99aed5a1420f8', 'points': '31918.50', 'elo': '3.6', 'error': '1.7'}, 
    {'date_committed': u'2014-11-18T22:39:17Z', 'sha': '0a1f54975fe3cb59a5274cbfee51f5b53e64071b', 'points': '31910.00', 'elo': '3.5', 'error': '1.7'}, 
    {'date_committed': u'2014-12-06T14:19:39Z', 'sha': '0935dca9a6729f8036b3bde3554708743e47ac43', 'points': '31902.50', 'elo': '3.4', 'error': '1.9'}, 
    {'date_committed': u'2014-11-16T23:04:58Z', 'sha': '3b1f552b08b254a5b2d8234ba35d52d3ee86a7cb', 'points': '31898.50', 'elo': '3.4', 'error': '1.8'}, 
    {'date_committed': u'2014-11-09T20:13:56Z', 'sha': 'd709a5f1c52f253a09cd931d06b5197dcdafc3ba', 'points': '31884.50', 'elo': '3.2', 'error': '1.9'}, 
    {'date_committed': u'2014-11-17T11:56:48Z', 'sha': '1a939cd8c8679e74e9a27ae72d9963247d647890', 'points': '31872.00', 'elo': '3.1', 'error': '1.7'}, 
    {'date_committed': u'2014-12-07T23:53:33Z', 'sha': 'fbb53524efd94c4b227c72c725c628a4aa5f9f72', 'points': '31865.50', 'elo': '3.0', 'error': '1.9'}, 
    {'date_committed': u'2014-12-08T00:18:26Z', 'sha': '158864270a055fe20dca4a87f4b7a8aa9cedfeb9', 'points': '31863.50', 'elo': '3.0', 'error': '1.9'}, 
    {'date_committed': u'2014-11-09T19:17:29Z', 'sha': '57fdfdedcf8c910fc9ad6c827a1a4dae372d3606', 'points': '31840.00', 'elo': '2.8', 'error': '1.7'}, 
    {'date_committed': u'2014-12-22T07:33:07Z', 'sha': '296534f23489e6d95ba7ce1bb35e8a2cbf9a5a9d', 'points': '31833.00', 'elo': '2.7', 'error': '1.9'}, 
    {'date_committed': u'2014-11-21T21:46:59Z', 'sha': '48127fe5d35b01c1cd1ffb8657ed73dfe5730da3', 'points': '31774.50', 'elo': '2.0', 'error': '1.9'}, 
    {'date_committed': u'2014-12-06T15:08:21Z', 'sha': 'ba1464751d1186f723a2d2a5d18c06ddfc9a4cb3', 'points': '31754.00', 'elo': '1.8', 'error': '2.0'}, 
    {'date_committed': u'2014-12-11T18:08:29Z', 'sha': 'f6d220ab145a361f7240a44dbe61056e801d9bda', 'points': '31742.50', 'elo': '1.7', 'error': '1.9'}, 
    {'date_committed': u'2014-12-18T19:57:04Z', 'sha': '46d5fff01fbeafdf822e440231845363ba979f09', 'points': '31742.00', 'elo': '1.7', 'error': '2.0'}, 
    {'date_committed': u'2014-11-10T23:06:12Z', 'sha': 'c6d45c60b516e799526f1163733b74b23fc1b63c', 'points': '31740.00', 'elo': '1.7', 'error': '1.8'}, 
    {'date_committed': u'2014-11-12T21:16:33Z', 'sha': '4739037f967ac3c818907e89cc88c7b97021d027', 'points': '31733.50', 'elo': '1.6', 'error': '2.0'}, 
    {'date_committed': u'2014-11-30T20:37:24Z', 'sha': '314d446518daa035526be8539b23957ba4678468', 'points': '31724.00', 'elo': '1.5', 'error': '2.0'}, 
    {'date_committed': u'2014-11-07T19:27:04Z', 'sha': '375797d51c8c18b98930f5e4c404b7fd572f6737', 'points': '31707.50', 'elo': '1.3', 'error': '1.9'}, 
    {'date_committed': u'2014-11-30T20:24:32Z', 'sha': 'c014444f09ace05e908909d9c5c60127e998b538', 'points': '31673.00', 'elo': '0.9', 'error': '2.0'}, 
    {'date_committed': u'2014-11-01T18:02:35Z', 'sha': '5644e14d0e3d69b3f845e475771564ffb3e25445', 'points': '31669.50', 'elo': '0.9', 'error': '2.0'}, 
    {'date_committed': u'2014-11-08T15:47:56Z', 'sha': '3d2aab11d89493311e0908a9ee1a8288b9ff9b42', 'points': '31666.50', 'elo': '0.8', 'error': '1.8'}, 
    {'date_committed': u'2014-11-18T22:37:59Z', 'sha': 'bffe32f4fe66decd0aa1bd7e39f808c33b3e9410', 'points': '31666.00', 'elo': '0.8', 'error': '1.9'}, 
    {'date_committed': u'2014-12-14T23:49:00Z', 'sha': '413b24380993cfdb7578ebe10b6a71b51bd8fb5b', 'points': '31639.00', 'elo': '0.5', 'error': '1.9'}, 
    {'date_committed': u'2014-11-30T19:53:04Z', 'sha': '9b4e123fbee44b0dc5d6aba497e5e70d165f576c', 'points': '31638.50', 'elo': '0.5', 'error': '1.9'}, 
    {'date_committed': u'2014-11-21T19:37:45Z', 'sha': '79232be02a03a5e2225b30f843e9597fd85951dc', 'points': '31638.00', 'elo': '0.5', 'error': '1.9'}, 
    {'date_committed': u'2014-11-08T15:56:51Z', 'sha': '8631b08d9704dac256462f6b5b885a4d8b0a9165', 'points': '31633.00', 'elo': '0.5', 'error': '2.0'}, 
    {'date_committed': u'2014-12-11T19:56:24Z', 'sha': '7b4828b68ced7e92a3399f9e48da8726b6b315f0', 'points': '31633.00', 'elo': '0.5', 'error': '1.9'}, 
    {'date_committed': u'2014-11-21T19:40:25Z', 'sha': '84408e5cd68a9323292ddababec4d1183abeef2e', 'points': '31623.50', 'elo': '0.4', 'error': '1.8'}, 
    {'date_committed': u'2014-11-12T21:06:14Z', 'sha': '234344500f4d6e35c6992a07e0b1adb59aea209e', 'points': '31614.00', 'elo': '0.3', 'error': '1.8'}, 
    {'date_committed': u'2014-11-30T19:23:17Z', 'sha': '66f5cd3f9d123306c509b6172fd11ed3afa1d39a', 'points': '31608.50', 'elo': '0.2', 'error': '1.8'}, 
    {'date_committed': u'2014-11-01T17:05:03Z', 'sha': 'd07a8753983d0cbe7d81e61136b304e771b57ba7', 'points': '31600.00', 'elo': '0.1', 'error': '1.9'}, 
    {'date_committed': u'2014-11-30T19:35:35Z', 'sha': 'a43f633c19c43b43ec7a5e460eb91b7abcf59e3a', 'points': '31598.00', 'elo': '0.1', 'error': '1.9'}, 
    {'date_committed': u'2014-11-25T23:55:57Z', 'sha': '2c52147dbfdc714a0ae95982f37fc5141b225f8c', 'points': '31585.00', 'elo': '-0.1', 'error': '1.9'}, 
    {'date_committed': u'2014-12-20T17:55:18Z', 'sha': 'e5c7b44f7abf49170ffba98940c7c8bf95806d07', 'points': '31578.50', 'elo': '-0.1', 'error': '1.8'}, 
    {'date_committed': u'2014-12-11T18:03:44Z', 'sha': 'afafdf7b73295b54a4027d88748599ff20f61759', 'points': '31574.50', 'elo': '-0.2', 'error': '2.1'}, 
    {'date_committed': u'2014-12-06T14:23:08Z', 'sha': '35c1ccef3962818339806f657eedba2da96bf18a', 'points': '31573.00', 'elo': '-0.2', 'error': '1.8'}, 
    {'date_committed': u'2014-11-01T20:50:52Z', 'sha': 'd3091971b789b4be4c56fdf608eae33c5c54bbd4', 'points': '31570.00', 'elo': '-0.2', 'error': '1.9'}, 
    {'date_committed': u'2014-11-24T00:53:00Z', 'sha': '4509eb1342fe282d08bd90340efaff4df5947a87', 'points': '31557.50', 'elo': '-0.4', 'error': '1.8'}, 
    {'date_committed': u'2014-11-25T23:49:58Z', 'sha': '7caa6cd3383cf90189a1947c9bdf9c6fea1172a6', 'points': '31551.00', 'elo': '-0.4', 'error': '1.8'}, 
    {'date_committed': u'2014-11-15T04:36:49Z', 'sha': '4840643fedbfc33d118cdc13c8435b062e3da99b', 'points': '31544.50', 'elo': '-0.5', 'error': '1.9'}, 
    {'date_committed': u'2014-11-01T20:43:57Z', 'sha': 'd9caede3249698440b7579e31d92aaa9984a128b', 'points': '31538.00', 'elo': '-0.6', 'error': '1.9'}, 
    {'date_committed': u'2014-11-09T09:27:04Z', 'sha': '6fb0a1bc4050dd9b15e9c163c46c60f25c48137d', 'points': '31537.50', 'elo': '-0.6', 'error': '2.0'}, 
    {'date_committed': u'2014-12-10T11:38:13Z', 'sha': '5943600a890cef1e83235d08b248e686c95c77d1', 'points': '31535.00', 'elo': '-0.6', 'error': '2.0'}, 
    {'date_committed': u'2014-12-06T14:35:50Z', 'sha': 'c30eb4c9c9f875a8302056ddd9612003bc21c023', 'points': '31526.50', 'elo': '-0.7', 'error': '2.0'}, 
    {'date_committed': u'2014-11-25T23:56:48Z', 'sha': 'fe07ae4cb4c2553fb48cab44c502ba766d1f09ce', 'points': '31523.00', 'elo': '-0.7', 'error': '2.0'}, 
    {'date_committed': u'2014-12-14T23:50:33Z', 'sha': 'b8fd1a78dc69f9baba2d8b0079e2d7844fe62958', 'points': '31517.50', 'elo': '-0.8', 'error': '1.8'}, 
    {'date_committed': u'2014-12-10T17:57:55Z', 'sha': '94dd204c3b10ebe0e6c8df5d7c98de5ba4906cad', 'points': '31509.50', 'elo': '-0.9', 'error': '1.8'}, 
    {'date_committed': u'2014-11-05T21:09:21Z', 'sha': 'd29a68f5854d0b529f2e0447fddcc6a61200c5aa', 'points': '31482.50', 'elo': '-1.2', 'error': '2.1'}, 
    {'date_committed': u'2014-12-19T10:06:40Z', 'sha': '9cae6e66ce00850086d1bfe1e24e34442c12b206', 'points': '31470.50', 'elo': '-1.3', 'error': '2.0'}, 
    {'date_committed': u'2014-11-01T20:35:10Z', 'sha': '8a7876d48d4360d14d918c1ff444b5d6eb0382de', 'points': '31457.50', 'elo': '-1.5', 'error': '2.0'}, 
    {'date_committed': u'2014-12-06T14:58:00Z', 'sha': 'eeb6d923fa5e773ba223c0cede75705c1f3d9e89', 'points': '31454.00', 'elo': '-1.5', 'error': '1.9'}, 
    {'date_committed': u'2014-11-03T16:35:02Z', 'sha': 'd12378497cb24f40d3510cdcfaecd1335f523196', 'points': '31365.50', 'elo': '-2.5', 'error': '1.9'}, 
    {'date_committed': u'2014-11-06T18:01:47Z', 'sha': '8e98bd616e33cbe2d5cd7a22867a29d29bd67a1b', 'points': '31356.00', 'elo': '-2.6', 'error': '1.9'}, 
    {'date_committed': u'2014-11-01T21:24:33Z', 'sha': '79fa72f392343fb93c16c133dedc3dbdf795e746', 'points': '31339.00', 'elo': '-2.8', 'error': '1.9'}, 
    {'date_committed': u'2014-12-10T11:35:21Z', 'sha': '589c711449ef09b459b76d8891b6abc5c0b843bd', 'points': '31320.00', 'elo': '-3.0', 'error': '1.8'}, 
    {'date_committed': u'2014-11-05T21:11:05Z', 'sha': 'bcbab1937670ca39ddb0a216ff9a787e56b79b3a', 'points': '31316.50', 'elo': '-3.0', 'error': '2.0'}, 
    {'date_committed': u'2014-12-10T17:59:41Z', 'sha': 'b15dcd977487c58409de48016eb7680850481d5d', 'points': '31283.00', 'elo': '-3.4', 'error': '1.9'}, 
    {'date_committed': u'2014-11-03T18:40:49Z', 'sha': '2fd075d1ea62e0d68c7044ec8d199067c901adaa', 'points': '31277.00', 'elo': '-3.4', 'error': '1.9'}, 
    {'date_committed': u'2014-11-01T20:16:29Z', 'sha': '2ee125029420b46b255116ab1d57931a9d6cf3e4', 'points': '31167.00', 'elo': '-4.7', 'error': '2.1'}, 
    {'date_committed': u'2014-11-05T21:17:19Z', 'sha': 'bc83515c9e821016d2113298ef988e99ceced1af', 'points': '31084.00', 'elo': '-5.6', 'error': '1.9'}, 
    {'date_committed': u'2014-11-07T21:40:24Z', 'sha': '7ebb872409d23b7c745d71ce5c21bea786d81aa0', 'points': '31021.00', 'elo': '-6.3', 'error': '2.1'}, 
    {'date_committed': u'2014-11-01T22:10:25Z', 'sha': '42a20920e5259dbe3efd9002fbc7176a9f071636', 'points': '30964.00', 'elo': '-6.9', 'error': '1.9'}, 
    {'date_committed': u'2014-11-02T07:03:52Z', 'sha': 'fc0733087a035b9e86e17f73b42215b583392502', 'points': '30906.00', 'elo': '-7.5', 'error': '1.9'}, 
    {'date_committed': u'2014-11-03T15:36:24Z', 'sha': '8ab9c2511a36a929a17a689125c919c927aee786', 'points': '30868.50', 'elo': '-7.9', 'error': '2.0'}, 
    {'date_committed': u'2014-11-04T15:50:54Z', 'sha': '0608d6aaec6fe841550c9fc7142bba1b50d9ead6', 'points': '30652.00', 'elo': '-10.3', 'error': '2.1'}, 
    {'date_committed': u'2014-05-31T21:34:36Z', 'sha': 'f5622cd5ec7836e899e263cc4cd4cc386e1ed5f4', 'points': '28276.50', 'elo': '-36.5', 'error': '1.9'}]},
  {'description': '04-01-14 Run 2', 'games':'58500', 'data': [
    {'date_committed': u'2014-12-25T10:09:07Z', 'sha': '2bfacf136cf780936aab3ddfb1dfce0163d09d40', 'points': '29894.00', 'elo': '7.7', 'error': '2.1'},
    {'date_committed': u'2014-12-28T18:06:56Z', 'sha': '6933f05f4b1b7b1bd2c072029bf5a06cbeac5b0b', 'points': '29859.00', 'elo': '7.2', 'error': '2.0'},
    {'date_committed': u'2014-12-14T19:45:43Z', 'sha': '0edb6348d20ec35a8ac65453239097078d947b7e', 'points': '29760.00', 'elo': '6.1', 'error': '1.9'},
    {'date_committed': u'2014-11-16T23:48:30Z', 'sha': '99f2c1a2a64cac94ee56324fa25f8fba04cd1347', 'points': '29729.50', 'elo': '5.7', 'error': '2.2'},
    {'date_committed': u'2014-11-12T21:02:20Z', 'sha': 'b777b17f6ff7fe9670d864cf31106fdefdca3001', 'points': '29699.50', 'elo': '5.3', 'error': '1.9'},
    {'date_committed': u'2014-12-13T07:22:37Z', 'sha': '14cf27e6f65787a1f9c8e4759ae0fcc218f37d2d', 'points': '29685.50', 'elo': '5.2', 'error': '2.1'},
    {'date_committed': u'2014-12-28T10:58:29Z', 'sha': 'f9571e8d57381275f08ffbfb960358319d4c34dd', 'points': '29659.50', 'elo': '4.9', 'error': '2.0'},
    {'date_committed': u'2014-12-07T23:53:33Z', 'sha': 'fbb53524efd94c4b227c72c725c628a4aa5f9f72', 'points': '29652.50', 'elo': '4.8', 'error': '1.9'},
    {'date_committed': u'2014-11-09T19:36:28Z', 'sha': '1b0df1ae141be1461e3fbe809b5b27c3e360753f', 'points': '29641.50', 'elo': '4.7', 'error': '2.1'},
    {'date_committed': u'2014-11-18T10:57:57Z', 'sha': '4aca11ae2a37df653b54f554a3d8b3005c063447', 'points': '29641.00', 'elo': '4.7', 'error': '2.1'},
    {'date_committed': u'2014-11-16T23:50:33Z', 'sha': 'd65c9a326294a1f7bedf8f9a386b155f10055b42', 'points': '29632.00', 'elo': '4.5', 'error': '1.9'},
    {'date_committed': u'2014-11-24T00:50:36Z', 'sha': '7ad59d9ac9cbeae8b95843a720a53c99bb1f0d3b', 'points': '29630.00', 'elo': '4.5', 'error': '2.0'},
    {'date_committed': u'2014-11-09T20:13:56Z', 'sha': 'd709a5f1c52f253a09cd931d06b5197dcdafc3ba', 'points': '29610.50', 'elo': '4.3', 'error': '2.0'},
    {'date_committed': u'2014-11-09T19:17:29Z', 'sha': '57fdfdedcf8c910fc9ad6c827a1a4dae372d3606', 'points': '29606.00', 'elo': '4.2', 'error': '1.9'},
    {'date_committed': u'2014-12-20T17:53:44Z', 'sha': '323103826274c6ea23d36fd05ef0744f8d38cd3f', 'points': '29593.50', 'elo': '4.1', 'error': '1.9'},
    {'date_committed': u'2014-11-12T21:00:16Z', 'sha': 'db4b8ee000912f88927757eb8dee255b8d66a4b4', 'points': '29584.50', 'elo': '4.0', 'error': '1.9'},
    {'date_committed': u'2014-11-18T22:39:17Z', 'sha': '0a1f54975fe3cb59a5274cbfee51f5b53e64071b', 'points': '29572.00', 'elo': '3.8', 'error': '1.9'},
    {'date_committed': u'2014-12-07T23:58:05Z', 'sha': 'a87da2c4b3dce975fa8642c352c99aed5a1420f8', 'points': '29560.00', 'elo': '3.7', 'error': '1.9'},
    {'date_committed': u'2014-11-16T23:04:58Z', 'sha': '3b1f552b08b254a5b2d8234ba35d52d3ee86a7cb', 'points': '29558.00', 'elo': '3.7', 'error': '1.7'},
    {'date_committed': u'2014-12-06T14:19:39Z', 'sha': '0935dca9a6729f8036b3bde3554708743e47ac43', 'points': '29542.50', 'elo': '3.5', 'error': '2.1'},
    {'date_committed': u'2014-11-12T21:16:33Z', 'sha': '4739037f967ac3c818907e89cc88c7b97021d027', 'points': '29493.00', 'elo': '2.9', 'error': '2.0'},
    {'date_committed': u'2014-11-17T11:56:48Z', 'sha': '1a939cd8c8679e74e9a27ae72d9963247d647890', 'points': '29490.50', 'elo': '2.9', 'error': '1.8'},
    {'date_committed': u'2014-12-08T00:18:26Z', 'sha': '158864270a055fe20dca4a87f4b7a8aa9cedfeb9', 'points': '29480.50', 'elo': '2.7', 'error': '2.1'},
    {'date_committed': u'2014-12-06T15:08:21Z', 'sha': 'ba1464751d1186f723a2d2a5d18c06ddfc9a4cb3', 'points': '29479.00', 'elo': '2.7', 'error': '2.2'},
    {'date_committed': u'2014-11-09T09:27:04Z', 'sha': '6fb0a1bc4050dd9b15e9c163c46c60f25c48137d', 'points': '29458.50', 'elo': '2.5', 'error': '1.9'},
    {'date_committed': u'2014-12-06T14:23:08Z', 'sha': '35c1ccef3962818339806f657eedba2da96bf18a', 'points': '29452.50', 'elo': '2.4', 'error': '2.0'},
    {'date_committed': u'2014-12-14T23:49:00Z', 'sha': '413b24380993cfdb7578ebe10b6a71b51bd8fb5b', 'points': '29446.50', 'elo': '2.3', 'error': '2.0'},
    {'date_committed': u'2014-12-22T07:33:07Z', 'sha': '296534f23489e6d95ba7ce1bb35e8a2cbf9a5a9d', 'points': '29439.00', 'elo': '2.3', 'error': '2.0'},
    {'date_committed': u'2014-11-30T20:37:24Z', 'sha': '314d446518daa035526be8539b23957ba4678468', 'points': '29436.50', 'elo': '2.2', 'error': '2.1'},
    {'date_committed': u'2014-12-18T19:57:04Z', 'sha': '46d5fff01fbeafdf822e440231845363ba979f09', 'points': '29435.50', 'elo': '2.2', 'error': '2.1'},
    {'date_committed': u'2014-11-10T23:06:12Z', 'sha': 'c6d45c60b516e799526f1163733b74b23fc1b63c', 'points': '29415.50', 'elo': '2.0', 'error': '1.9'},
    {'date_committed': u'2014-12-20T17:55:18Z', 'sha': 'e5c7b44f7abf49170ffba98940c7c8bf95806d07', 'points': '29404.50', 'elo': '1.8', 'error': '1.9'},
    {'date_committed': u'2014-11-08T15:47:56Z', 'sha': '3d2aab11d89493311e0908a9ee1a8288b9ff9b42', 'points': '29396.50', 'elo': '1.7', 'error': '1.8'},
    {'date_committed': u'2014-11-24T00:53:00Z', 'sha': '4509eb1342fe282d08bd90340efaff4df5947a87', 'points': '29366.00', 'elo': '1.4', 'error': '1.8'},
    {'date_committed': u'2014-11-30T20:24:32Z', 'sha': 'c014444f09ace05e908909d9c5c60127e998b538', 'points': '29354.50', 'elo': '1.2', 'error': '2.0'},
    {'date_committed': u'2014-11-18T22:37:59Z', 'sha': 'bffe32f4fe66decd0aa1bd7e39f808c33b3e9410', 'points': '29324.50', 'elo': '0.9', 'error': '2.0'},
    {'date_committed': u'2014-12-11T18:08:29Z', 'sha': 'f6d220ab145a361f7240a44dbe61056e801d9bda', 'points': '29320.50', 'elo': '0.8', 'error': '1.9'},
    {'date_committed': u'2014-11-21T21:46:59Z', 'sha': '48127fe5d35b01c1cd1ffb8657ed73dfe5730da3', 'points': '29318.00', 'elo': '0.8', 'error': '1.9'},
    {'date_committed': u'2014-11-01T18:02:35Z', 'sha': '5644e14d0e3d69b3f845e475771564ffb3e25445', 'points': '29311.00', 'elo': '0.7', 'error': '2.1'},
    {'date_committed': u'2014-11-25T23:55:57Z', 'sha': '2c52147dbfdc714a0ae95982f37fc5141b225f8c', 'points': '29291.00', 'elo': '0.5', 'error': '2.0'},
    {'date_committed': u'2014-12-10T11:38:13Z', 'sha': '5943600a890cef1e83235d08b248e686c95c77d1', 'points': '29261.50', 'elo': '0.1', 'error': '2.1'},
    {'date_committed': u'2014-11-30T19:35:35Z', 'sha': 'a43f633c19c43b43ec7a5e460eb91b7abcf59e3a', 'points': '29247.50', 'elo': '-0.0', 'error': '2.1'},
    {'date_committed': u'2014-11-12T21:06:14Z', 'sha': '234344500f4d6e35c6992a07e0b1adb59aea209e', 'points': '29237.00', 'elo': '-0.2', 'error': '1.9'},
    {'date_committed': u'2014-11-07T19:27:04Z', 'sha': '375797d51c8c18b98930f5e4c404b7fd572f6737', 'points': '29232.50', 'elo': '-0.2', 'error': '1.9'},
    {'date_committed': u'2014-11-15T04:36:49Z', 'sha': '4840643fedbfc33d118cdc13c8435b062e3da99b', 'points': '29232.50', 'elo': '-0.2', 'error': '1.8'},
    {'date_committed': u'2014-11-21T19:40:25Z', 'sha': '84408e5cd68a9323292ddababec4d1183abeef2e', 'points': '29231.50', 'elo': '-0.2', 'error': '1.9'},
    {'date_committed': u'2014-12-19T10:06:40Z', 'sha': '9cae6e66ce00850086d1bfe1e24e34442c12b206', 'points': '29220.00', 'elo': '-0.4', 'error': '2.0'},
    {'date_committed': u'2014-11-01T17:05:03Z', 'sha': 'd07a8753983d0cbe7d81e61136b304e771b57ba7', 'points': '29207.00', 'elo': '-0.5', 'error': '2.1'},
    {'date_committed': u'2014-11-25T23:56:48Z', 'sha': 'fe07ae4cb4c2553fb48cab44c502ba766d1f09ce', 'points': '29200.50', 'elo': '-0.6', 'error': '1.9'},
    {'date_committed': u'2014-11-01T20:50:52Z', 'sha': 'd3091971b789b4be4c56fdf608eae33c5c54bbd4', 'points': '29193.50', 'elo': '-0.7', 'error': '1.9'},
    {'date_committed': u'2014-12-11T19:56:24Z', 'sha': '7b4828b68ced7e92a3399f9e48da8726b6b315f0', 'points': '29180.50', 'elo': '-0.8', 'error': '1.8'},
    {'date_committed': u'2014-12-06T14:35:50Z', 'sha': 'c30eb4c9c9f875a8302056ddd9612003bc21c023', 'points': '29171.00', 'elo': '-0.9', 'error': '1.9'},
    {'date_committed': u'2014-11-30T19:53:04Z', 'sha': '9b4e123fbee44b0dc5d6aba497e5e70d165f576c', 'points': '29168.00', 'elo': '-1.0', 'error': '2.0'},
    {'date_committed': u'2014-11-08T15:56:51Z', 'sha': '8631b08d9704dac256462f6b5b885a4d8b0a9165', 'points': '29165.50', 'elo': '-1.0', 'error': '2.1'},
    {'date_committed': u'2014-12-06T14:58:00Z', 'sha': 'eeb6d923fa5e773ba223c0cede75705c1f3d9e89', 'points': '29159.50', 'elo': '-1.1', 'error': '2.0'},
    {'date_committed': u'2014-11-01T21:24:33Z', 'sha': '79fa72f392343fb93c16c133dedc3dbdf795e746', 'points': '29144.00', 'elo': '-1.3', 'error': '2.0'},
    {'date_committed': u'2014-11-05T21:09:21Z', 'sha': 'd29a68f5854d0b529f2e0447fddcc6a61200c5aa', 'points': '29131.50', 'elo': '-1.4', 'error': '2.2'},
    {'date_committed': u'2014-11-25T23:49:58Z', 'sha': '7caa6cd3383cf90189a1947c9bdf9c6fea1172a6', 'points': '29127.50', 'elo': '-1.5', 'error': '2.1'},
    {'date_committed': u'2014-11-21T19:37:45Z', 'sha': '79232be02a03a5e2225b30f843e9597fd85951dc', 'points': '29119.50', 'elo': '-1.6', 'error': '2.0'},
    {'date_committed': u'2014-11-30T19:23:17Z', 'sha': '66f5cd3f9d123306c509b6172fd11ed3afa1d39a', 'points': '29098.50', 'elo': '-1.8', 'error': '1.9'},
    {'date_committed': u'2014-11-06T18:01:47Z', 'sha': '8e98bd616e33cbe2d5cd7a22867a29d29bd67a1b', 'points': '29059.50', 'elo': '-2.3', 'error': '2.1'},
    {'date_committed': u'2014-12-11T18:03:44Z', 'sha': 'afafdf7b73295b54a4027d88748599ff20f61759', 'points': '29041.50', 'elo': '-2.5', 'error': '2.2'},
    {'date_committed': u'2014-11-01T20:35:10Z', 'sha': '8a7876d48d4360d14d918c1ff444b5d6eb0382de', 'points': '29035.00', 'elo': '-2.6', 'error': '2.0'},
    {'date_committed': u'2014-12-10T17:57:55Z', 'sha': '94dd204c3b10ebe0e6c8df5d7c98de5ba4906cad', 'points': '29024.00', 'elo': '-2.7', 'error': '1.9'},
    {'date_committed': u'2014-12-14T23:50:33Z', 'sha': 'b8fd1a78dc69f9baba2d8b0079e2d7844fe62958', 'points': '29017.00', 'elo': '-2.8', 'error': '2.0'},
    {'date_committed': u'2014-11-01T20:43:57Z', 'sha': 'd9caede3249698440b7579e31d92aaa9984a128b', 'points': '29005.50', 'elo': '-2.9', 'error': '1.9'},
    {'date_committed': u'2014-12-10T11:35:21Z', 'sha': '589c711449ef09b459b76d8891b6abc5c0b843bd', 'points': '29001.00', 'elo': '-3.0', 'error': '1.9'},
    {'date_committed': u'2014-11-03T18:40:49Z', 'sha': '2fd075d1ea62e0d68c7044ec8d199067c901adaa', 'points': '28992.00', 'elo': '-3.1', 'error': '1.8'},
    {'date_committed': u'2014-11-03T16:35:02Z', 'sha': 'd12378497cb24f40d3510cdcfaecd1335f523196', 'points': '28941.00', 'elo': '-3.7', 'error': '1.9'},
    {'date_committed': u'2014-11-05T21:11:05Z', 'sha': 'bcbab1937670ca39ddb0a216ff9a787e56b79b3a', 'points': '28940.50', 'elo': '-3.7', 'error': '2.2'},
    {'date_committed': u'2014-11-01T20:16:29Z', 'sha': '2ee125029420b46b255116ab1d57931a9d6cf3e4', 'points': '28898.00', 'elo': '-4.2', 'error': '2.2'},
    {'date_committed': u'2014-12-10T17:59:41Z', 'sha': 'b15dcd977487c58409de48016eb7680850481d5d', 'points': '28866.00', 'elo': '-4.6', 'error': '1.9'},
    {'date_committed': u'2014-11-05T21:17:19Z', 'sha': 'bc83515c9e821016d2113298ef988e99ceced1af', 'points': '28858.00', 'elo': '-4.7', 'error': '1.9'},
    {'date_committed': u'2014-11-07T21:40:24Z', 'sha': '7ebb872409d23b7c745d71ce5c21bea786d81aa0', 'points': '28705.50', 'elo': '-6.5', 'error': '1.9'},
    {'date_committed': u'2014-11-03T15:36:24Z', 'sha': '8ab9c2511a36a929a17a689125c919c927aee786', 'points': '28641.50', 'elo': '-7.2', 'error': '2.0'},
    {'date_committed': u'2014-11-02T07:03:52Z', 'sha': 'fc0733087a035b9e86e17f73b42215b583392502', 'points': '28640.00', 'elo': '-7.3', 'error': '2.0'},
    {'date_committed': u'2014-11-01T22:10:25Z', 'sha': '42a20920e5259dbe3efd9002fbc7176a9f071636', 'points': '28628.50', 'elo': '-7.4', 'error': '1.9'},
    {'date_committed': u'2014-11-04T15:50:54Z', 'sha': '0608d6aaec6fe841550c9fc7142bba1b50d9ead6', 'points': '28296.00', 'elo': '-11.3', 'error': '2.1'},
    {'date_committed': u'2014-05-31T21:34:36Z', 'sha': 'f5622cd5ec7836e899e263cc4cd4cc386e1ed5f4', 'points': '26206.00', 'elo': '-36.2', 'error': '2.1'}]},
  {'description': '04-01-14 Run 1', 'games':'63180', 'data': [
    {'sha': '2bfacf136cf780936aab3ddfb1dfce0163d09d40', 'points': '32307.50', 'date_committed': u'2014-12-25T10:09:07Z', 'elo': '7.9', 'error': '2.0'},
    {'sha': 'b777b17f6ff7fe9670d864cf31106fdefdca3001', 'points': '32267.50', 'date_committed': u'2014-11-12T21:02:20Z', 'elo': '7.4', 'error': '2.0'},
    {'sha': '0edb6348d20ec35a8ac65453239097078d947b7e', 'points': '32251.50', 'date_committed': u'2014-12-14T19:45:43Z', 'elo': '7.3', 'error': '1.9'},
    {'sha': '14cf27e6f65787a1f9c8e4759ae0fcc218f37d2d', 'points': '32212.50', 'date_committed': u'2014-12-13T07:22:37Z', 'elo': '6.8', 'error': '2.0'},
    {'sha': '99f2c1a2a64cac94ee56324fa25f8fba04cd1347', 'points': '32182.00', 'date_committed': u'2014-11-16T23:48:30Z', 'elo': '6.5', 'error': '2.0'},
    {'sha': '4aca11ae2a37df653b54f554a3d8b3005c063447', 'points': '32122.00', 'date_committed': u'2014-11-18T10:57:57Z', 'elo': '5.8', 'error': '1.9'},
    {'sha': 'd65c9a326294a1f7bedf8f9a386b155f10055b42', 'points': '32046.00', 'date_committed': u'2014-11-16T23:50:33Z', 'elo': '5.0', 'error': '2.0'},
    {'sha': '6933f05f4b1b7b1bd2c072029bf5a06cbeac5b0b', 'points': '32040.50', 'date_committed': u'2014-12-28T18:06:56Z', 'elo': '5.0', 'error': '2.0'},
    {'sha': '7ad59d9ac9cbeae8b95843a720a53c99bb1f0d3b', 'points': '32024.50', 'date_committed': u'2014-11-24T00:50:36Z', 'elo': '4.8', 'error': '1.8'},
    {'sha': '1a939cd8c8679e74e9a27ae72d9963247d647890', 'points': '32005.50', 'date_committed': u'2014-11-17T11:56:48Z', 'elo': '4.6', 'error': '1.7'},
    {'sha': 'f9571e8d57381275f08ffbfb960358319d4c34dd', 'points': '31996.50', 'date_committed': u'2014-12-28T10:58:29Z', 'elo': '4.5', 'error': '1.9'},
    {'sha': 'd709a5f1c52f253a09cd931d06b5197dcdafc3ba', 'points': '31986.00', 'date_committed': u'2014-11-09T20:13:56Z', 'elo': '4.4', 'error': '1.9'},
    {'sha': '158864270a055fe20dca4a87f4b7a8aa9cedfeb9', 'points': '31969.50', 'date_committed': u'2014-12-08T00:18:26Z', 'elo': '4.2', 'error': '1.9'},
    {'sha': 'a87da2c4b3dce975fa8642c352c99aed5a1420f8', 'points': '31945.50', 'date_committed': u'2014-12-07T23:58:05Z', 'elo': '3.9', 'error': '1.7'},
    {'sha': 'fbb53524efd94c4b227c72c725c628a4aa5f9f72', 'points': '31930.50', 'date_committed': u'2014-12-07T23:53:33Z', 'elo': '3.7', 'error': '1.9'},
    {'sha': '35c1ccef3962818339806f657eedba2da96bf18a', 'points': '31888.00', 'date_committed': u'2014-12-06T14:23:08Z', 'elo': '3.3', 'error': '1.8'},
    {'sha': 'f6d220ab145a361f7240a44dbe61056e801d9bda', 'points': '31843.00', 'date_committed': u'2014-12-11T18:08:29Z', 'elo': '2.8', 'error': '1.9'},
    {'sha': '4739037f967ac3c818907e89cc88c7b97021d027', 'points': '31841.00', 'date_committed': u'2014-11-12T21:16:33Z', 'elo': '2.8', 'error': '2.0'},
    {'sha': 'db4b8ee000912f88927757eb8dee255b8d66a4b4', 'points': '31839.00', 'date_committed': u'2014-11-12T21:00:16Z', 'elo': '2.7', 'error': '1.9'},
    {'sha': '314d446518daa035526be8539b23957ba4678468', 'points': '31836.50', 'date_committed': u'2014-11-30T20:37:24Z', 'elo': '2.7', 'error': '2.0'},
    {'sha': '0935dca9a6729f8036b3bde3554708743e47ac43', 'points': '31825.50', 'date_committed': u'2014-12-06T14:19:39Z', 'elo': '2.6', 'error': '1.9'},
    {'sha': '413b24380993cfdb7578ebe10b6a71b51bd8fb5b', 'points': '31820.00', 'date_committed': u'2014-12-14T23:49:00Z', 'elo': '2.5', 'error': '1.9'},
    {'sha': '84408e5cd68a9323292ddababec4d1183abeef2e', 'points': '31816.50', 'date_committed': u'2014-11-21T19:40:25Z', 'elo': '2.5', 'error': '1.8'},
    {'sha': '1b0df1ae141be1461e3fbe809b5b27c3e360753f', 'points': '31786.50', 'date_committed': u'2014-11-09T19:36:28Z', 'elo': '2.2', 'error': '2.0'},
    {'sha': '296534f23489e6d95ba7ce1bb35e8a2cbf9a5a9d', 'points': '31778.00', 'date_committed': u'2014-12-22T07:33:07Z', 'elo': '2.1', 'error': '1.9'},
    {'sha': 'd9caede3249698440b7579e31d92aaa9984a128b', 'points': '31765.00', 'date_committed': u'2014-11-01T20:43:57Z', 'elo': '1.9', 'error': '1.9'},
    {'sha': '3b1f552b08b254a5b2d8234ba35d52d3ee86a7cb', 'points': '31755.00', 'date_committed': u'2014-11-16T23:04:58Z', 'elo': '1.8', 'error': '1.8'},
    {'sha': 'c6d45c60b516e799526f1163733b74b23fc1b63c', 'points': '31743.50', 'date_committed': u'2014-11-10T23:06:12Z', 'elo': '1.7', 'error': '1.8'},
    {'sha': '234344500f4d6e35c6992a07e0b1adb59aea209e', 'points': '31738.00', 'date_committed': u'2014-11-12T21:06:14Z', 'elo': '1.6', 'error': '1.8'},
    {'sha': '48127fe5d35b01c1cd1ffb8657ed73dfe5730da3', 'points': '31702.00', 'date_committed': u'2014-11-21T21:46:59Z', 'elo': '1.2', 'error': '1.9'},
    {'sha': '6fb0a1bc4050dd9b15e9c163c46c60f25c48137d', 'points': '31699.50', 'date_committed': u'2014-11-09T09:27:04Z', 'elo': '1.2', 'error': '2.0'},
    {'sha': '7b4828b68ced7e92a3399f9e48da8726b6b315f0', 'points': '31691.00', 'date_committed': u'2014-12-11T19:56:24Z', 'elo': '1.1', 'error': '1.9'},
    {'sha': 'ba1464751d1186f723a2d2a5d18c06ddfc9a4cb3', 'points': '31690.50', 'date_committed': u'2014-12-06T15:08:21Z', 'elo': '1.1', 'error': '1.9'},
    {'sha': '57fdfdedcf8c910fc9ad6c827a1a4dae372d3606', 'points': '31689.00', 'date_committed': u'2014-11-09T19:17:29Z', 'elo': '1.1', 'error': '1.8'},
    {'sha': '5644e14d0e3d69b3f845e475771564ffb3e25445', 'points': '31687.00', 'date_committed': u'2014-11-01T18:02:35Z', 'elo': '1.1', 'error': '2.0'},
    {'sha': '375797d51c8c18b98930f5e4c404b7fd572f6737', 'points': '31686.50', 'date_committed': u'2014-11-07T19:27:04Z', 'elo': '1.1', 'error': '1.9'},
    {'sha': 'c014444f09ace05e908909d9c5c60127e998b538', 'points': '31672.00', 'date_committed': u'2014-11-30T20:24:32Z', 'elo': '0.9', 'error': '2.0'},
    {'sha': '46d5fff01fbeafdf822e440231845363ba979f09', 'points': '31662.00', 'date_committed': u'2014-12-18T19:57:04Z', 'elo': '0.8', 'error': '2.0'},
    {'sha': '323103826274c6ea23d36fd05ef0744f8d38cd3f', 'points': '31644.50', 'date_committed': u'2014-12-20T17:53:44Z', 'elo': '0.6', 'error': '1.8'},
    {'sha': '4509eb1342fe282d08bd90340efaff4df5947a87', 'points': '31633.50', 'date_committed': u'2014-11-24T00:53:00Z', 'elo': '0.5', 'error': '1.8'},
    {'sha': 'a43f633c19c43b43ec7a5e460eb91b7abcf59e3a', 'points': '31605.00', 'date_committed': u'2014-11-30T19:35:35Z', 'elo': '0.2', 'error': '1.9'},
    {'sha': 'd07a8753983d0cbe7d81e61136b304e771b57ba7', 'points': '31600.00', 'date_committed': u'2014-11-01T17:05:03Z', 'elo': '0.1', 'error': '1.9'},
    {'sha': '0a1f54975fe3cb59a5274cbfee51f5b53e64071b', 'points': '31598.50', 'date_committed': u'2014-11-18T22:39:17Z', 'elo': '0.1', 'error': '1.7'},
    {'sha': '7caa6cd3383cf90189a1947c9bdf9c6fea1172a6', 'points': '31595.00', 'date_committed': u'2014-11-25T23:49:58Z', 'elo': '0.1', 'error': '1.8'},
    {'sha': '79232be02a03a5e2225b30f843e9597fd85951dc', 'points': '31590.50', 'date_committed': u'2014-11-21T19:37:45Z', 'elo': '0.0', 'error': '1.9'},
    {'sha': '4840643fedbfc33d118cdc13c8435b062e3da99b', 'points': '31584.50', 'date_committed': u'2014-11-15T04:36:49Z', 'elo': '-0.1', 'error': '1.9'},
    {'sha': 'bffe32f4fe66decd0aa1bd7e39f808c33b3e9410', 'points': '31575.00', 'date_committed': u'2014-11-18T22:37:59Z', 'elo': '-0.2', 'error': '1.9'},
    {'sha': '8a7876d48d4360d14d918c1ff444b5d6eb0382de', 'points': '31566.00', 'date_committed': u'2014-11-01T20:35:10Z', 'elo': '-0.3', 'error': '2.0'},
    {'sha': '8631b08d9704dac256462f6b5b885a4d8b0a9165', 'points': '31565.00', 'date_committed': u'2014-11-08T15:56:51Z', 'elo': '-0.3', 'error': '2.0'},
    {'sha': 'afafdf7b73295b54a4027d88748599ff20f61759', 'points': '31559.00', 'date_committed': u'2014-12-11T18:03:44Z', 'elo': '-0.3', 'error': '2.1'},
    {'sha': 'd3091971b789b4be4c56fdf608eae33c5c54bbd4', 'points': '31557.00', 'date_committed': u'2014-11-01T20:50:52Z', 'elo': '-0.4', 'error': '1.9'},
    {'sha': 'e5c7b44f7abf49170ffba98940c7c8bf95806d07', 'points': '31535.50', 'date_committed': u'2014-12-20T17:55:18Z', 'elo': '-0.6', 'error': '1.7'},
    {'sha': '2fd075d1ea62e0d68c7044ec8d199067c901adaa', 'points': '31531.50', 'date_committed': u'2014-11-03T18:40:49Z', 'elo': '-0.6', 'error': '1.9'},
    {'sha': '2c52147dbfdc714a0ae95982f37fc5141b225f8c', 'points': '31516.00', 'date_committed': u'2014-11-25T23:55:57Z', 'elo': '-0.8', 'error': '1.9'},
    {'sha': 'd29a68f5854d0b529f2e0447fddcc6a61200c5aa', 'points': '31511.50', 'date_committed': u'2014-11-05T21:09:21Z', 'elo': '-0.9', 'error': '2.1'},
    {'sha': 'c30eb4c9c9f875a8302056ddd9612003bc21c023', 'points': '31511.00', 'date_committed': u'2014-12-06T14:35:50Z', 'elo': '-0.9', 'error': '2.0'},
    {'sha': '66f5cd3f9d123306c509b6172fd11ed3afa1d39a', 'points': '31482.50', 'date_committed': u'2014-11-30T19:23:17Z', 'elo': '-1.2', 'error': '1.8'},
    {'sha': '5943600a890cef1e83235d08b248e686c95c77d1', 'points': '31482.00', 'date_committed': u'2014-12-10T11:38:13Z', 'elo': '-1.2', 'error': '2.0'},
    {'sha': '9b4e123fbee44b0dc5d6aba497e5e70d165f576c', 'points': '31460.00', 'date_committed': u'2014-11-30T19:53:04Z', 'elo': '-1.4', 'error': '1.9'},
    {'sha': '3d2aab11d89493311e0908a9ee1a8288b9ff9b42', 'points': '31457.50', 'date_committed': u'2014-11-08T15:47:56Z', 'elo': '-1.5', 'error': '1.9'},
    {'sha': '79fa72f392343fb93c16c133dedc3dbdf795e746', 'points': '31455.00', 'date_committed': u'2014-11-01T21:24:33Z', 'elo': '-1.5', 'error': '1.9'},
    {'sha': '2ee125029420b46b255116ab1d57931a9d6cf3e4', 'points': '31441.00', 'date_committed': u'2014-11-01T20:16:29Z', 'elo': '-1.6', 'error': '2.1'},
    {'sha': '8e98bd616e33cbe2d5cd7a22867a29d29bd67a1b', 'points': '31428.00', 'date_committed': u'2014-11-06T18:01:47Z', 'elo': '-1.8', 'error': '1.9'},
    {'sha': '9cae6e66ce00850086d1bfe1e24e34442c12b206', 'points': '31421.00', 'date_committed': u'2014-12-19T10:06:40Z', 'elo': '-1.9', 'error': '2.0'},
    {'sha': 'fe07ae4cb4c2553fb48cab44c502ba766d1f09ce', 'points': '31406.00', 'date_committed': u'2014-11-25T23:56:48Z', 'elo': '-2.0', 'error': '2.0'},
    {'sha': 'eeb6d923fa5e773ba223c0cede75705c1f3d9e89', 'points': '31348.00', 'date_committed': u'2014-12-06T14:58:00Z', 'elo': '-2.7', 'error': '1.9'},
    {'sha': '589c711449ef09b459b76d8891b6abc5c0b843bd', 'points': '31337.50', 'date_committed': u'2014-12-10T11:35:21Z', 'elo': '-2.8', 'error': '1.8'},
    {'sha': 'b8fd1a78dc69f9baba2d8b0079e2d7844fe62958', 'points': '31329.00', 'date_committed': u'2014-12-14T23:50:33Z', 'elo': '-2.9', 'error': '1.8'},
    {'sha': 'bcbab1937670ca39ddb0a216ff9a787e56b79b3a', 'points': '31230.00', 'date_committed': u'2014-11-05T21:11:05Z', 'elo': '-4.0', 'error': '2.0'},
    {'sha': '94dd204c3b10ebe0e6c8df5d7c98de5ba4906cad', 'points': '31228.50', 'date_committed': u'2014-12-10T17:57:55Z', 'elo': '-4.0', 'error': '1.8'},
    {'sha': 'bc83515c9e821016d2113298ef988e99ceced1af', 'points': '31218.00', 'date_committed': u'2014-11-05T21:17:19Z', 'elo': '-4.1', 'error': '1.9'},
    {'sha': 'd12378497cb24f40d3510cdcfaecd1335f523196', 'points': '31201.00', 'date_committed': u'2014-11-03T16:35:02Z', 'elo': '-4.3', 'error': '1.9'},
    {'sha': '7ebb872409d23b7c745d71ce5c21bea786d81aa0', 'points': '31188.00', 'date_committed': u'2014-11-07T21:40:24Z', 'elo': '-4.4', 'error': '2.1'},
    {'sha': 'b15dcd977487c58409de48016eb7680850481d5d', 'points': '31173.50', 'date_committed': u'2014-12-10T17:59:41Z', 'elo': '-4.6', 'error': '1.9'},
    {'sha': '8ab9c2511a36a929a17a689125c919c927aee786', 'points': '30971.50', 'date_committed': u'2014-11-03T15:36:24Z', 'elo': '-6.8', 'error': '2.0'},
    {'sha': '42a20920e5259dbe3efd9002fbc7176a9f071636', 'points': '30910.50', 'date_committed': u'2014-11-01T22:10:25Z', 'elo': '-7.5', 'error': '1.9'},
    {'sha': 'fc0733087a035b9e86e17f73b42215b583392502', 'points': '30889.50', 'date_committed': u'2014-11-02T07:03:52Z', 'elo': '-7.7', 'error': '1.9'},
    {'sha': '0608d6aaec6fe841550c9fc7142bba1b50d9ead6', 'points': '30706.00', 'date_committed': u'2014-11-04T15:50:54Z', 'elo': '-9.7', 'error': '2.1'},
    {'sha': 'f5622cd5ec7836e899e263cc4cd4cc386e1ed5f4', 'points': '27824.50', 'date_committed': u'2014-05-31T21:34:36Z', 'elo': '-41.6', 'error': '1.9'}]
  }];

  return {
    'fishtest': json.dumps(fishtest_regression_data),
    'jenstest': json.dumps(jenslehmann_regression_data)
  }

def parse_spsa_params(raw, spsa):
  params = []
  for line in raw.split('\n'):
    chunks = line.strip().split(',')
    if len(chunks) == 0:
      continue
    if len(chunks) != 6:
      raise Exception('"%s" needs 6 parameters"' % (line))
    param = {
      'name': chunks[0],
      'start': float(chunks[1]),
      'min': float(chunks[2]),
      'max': float(chunks[3]),
      'c_end': float(chunks[4]),
      'r_end': float(chunks[5]),
    }
    param['c'] = param['c_end'] * spsa['num_iter'] ** spsa['gamma']
    param['a_end'] = param['r_end'] * param['c_end'] ** 2
    param['a'] = param['a_end'] * (spsa['A'] + spsa['num_iter']) ** spsa['alpha']
    param['theta'] = param['start']

    params.append(param)

  return params

def validate_form(request):
  data = {
    'base_tag' : request.POST['base-branch'],
    'new_tag' : request.POST['test-branch'],
    'tc' : request.POST['tc'],
    'book' : request.POST['book'],
    'book_depth' : request.POST['book-depth'],
    'base_signature' : request.POST['base-signature'],
    'new_signature' : request.POST['test-signature'],
    'base_options' : request.POST['base-options'],
    'new_options' : request.POST['new-options'],
    'username' : authenticated_userid(request),
    'tests_repo' : request.POST['tests-repo'],
  }

  if len([v for v in data.values() if len(v) == 0]) > 0:
    raise Exception('Missing required option')

  data['regression_test'] = request.POST['test_type'] == 'Regression'
  if data['regression_test']:
    data['base_tag'] = data['new_tag']
    data['base_signature'] = data['new_signature']
    data['base_options'] = data['new_options']

  # In case of reschedule use old data, otherwise resolve sha and update user's tests_repo
  if 'resolved_base' in request.POST:
    data['resolved_base'] = request.POST['resolved_base']
    data['resolved_new'] = request.POST['resolved_new']
    data['msg_base'] = request.POST['msg_base']
    data['msg_new'] = request.POST['msg_new']
  else:
    data['resolved_base'], data['msg_base'] = get_sha(data['base_tag'], data['tests_repo'])
    data['resolved_new'], data['msg_new'] = get_sha(data['new_tag'], data['tests_repo'])
    u = request.userdb.get_user(data['username'])
    if u.get('tests_repo', '') != data['tests_repo']:
      u['tests_repo'] = data['tests_repo']
      request.userdb.users.save(u)

  if len(data['resolved_base']) == 0 or len(data['resolved_new']) == 0:
    raise Exception('Unable to find branch!')

  stop_rule = request.POST['stop_rule']

  # Integer parameters
  if stop_rule == 'sprt':
    data['sprt'] = {
      'elo0': float(request.POST['sprt_elo0']),
      'alpha': 0.05,
      'elo1': float(request.POST['sprt_elo1']),
      'beta': 0.05,
      'drawelo': 240.0,
    }
    # Arbitrary limit on number of games played.  Shouldn't be hit in practice
    data['num_games'] = 128000
  elif stop_rule == 'spsa':
    data['num_games'] = int(request.POST['num-games'])
    if data['num_games'] <= 0:
      raise Exception('Number of games must be >= 0')

    data['spsa'] = {
      'A': int(request.POST['spsa_A']),
      'alpha': float(request.POST['spsa_alpha']),
      'gamma': float(request.POST['spsa_gamma']),
      'raw_params': request.POST['spsa_raw_params'],
      'iter': 0,
      'num_iter': int(data['num_games'] / 2),
    }
    data['spsa']['params'] = parse_spsa_params(request.POST['spsa_raw_params'], data['spsa'])
  else:
    data['num_games'] = int(request.POST['num-games'])
    if data['num_games'] <= 0:
      raise Exception('Number of games must be >= 0')

  data['threads'] = int(request.POST['threads'])
  data['priority'] = int(request.POST['priority'])

  if data['threads'] <= 0:
    raise Exception('Threads must be >= 1')

  # Optional
  data['info'] = request.POST['run-info']

  return data

@view_config(route_name='tests_run', renderer='tests_run.mak', permission='modify_db')
def tests_run(request):
  if 'base-branch' in request.POST:
    try:
      data = validate_form(request)
      run_id = request.rundb.new_run(**data)

      request.actiondb.new_run(authenticated_userid(request), request.rundb.get_run(run_id))
      request.session.flash('Started test run!')
      return HTTPFound(location=request.route_url('tests'))
    except Exception as e:
      request.session.flash(str(e))

  run_args = {}
  if 'id' in request.params:
    run_args = request.rundb.get_run(request.params['id'])['args']

  username = authenticated_userid(request)
  u = request.userdb.get_user(username)

  return { 'args': run_args, 'tests_repo': u.get('tests_repo', '') }

def can_modify_run(request, run):
  return run['args']['username'] == authenticated_userid(request) or has_permission('approve_run', request.context, request)

@view_config(route_name='tests_modify', permission='modify_db')
def tests_modify(request):
  if 'num-games' in request.POST:
    run = request.rundb.get_run(request.POST['run'])
    before = copy.deepcopy(run)

    if not can_modify_run(request, run):
      request.session.flash('Unable to modify another users run!')
      return HTTPFound(location=request.route_url('tests'))

    existing_games = 0
    for chunk in run['tasks']:
      existing_games += chunk['num_games']

    num_games = int(request.POST['num-games'])
    if num_games > run['args']['num_games'] and not ('sprt' in run['args'] or 'spsa' in run['args']):
      request.session.flash('Unable to modify number of games in a fixed game test!')
      return HTTPFound(location=request.route_url('tests'))

    if num_games > existing_games:
      # Create new chunks for the games
      new_chunks = request.rundb.generate_tasks(num_games - existing_games)
      run['tasks'] += new_chunks

    run['finished'] = False
    run['args']['num_games'] = num_games
    run['args']['priority'] = int(request.POST['priority'])
    request.rundb.runs.save(run)

    request.actiondb.modify_run(authenticated_userid(request), before, run)

    request.session.flash('Run successfully modified!')
    return HTTPFound(location=request.route_url('tests'))
  return {}

@view_config(route_name='tests_stop', permission='modify_db')
def tests_stop(request):
  run = request.rundb.get_run(request.POST['run-id'])
  if not can_modify_run(request, run):
    request.session.flash('Unable to modify another users run!')
    return HTTPFound(location=request.route_url('tests'))

  request.rundb.stop_run(request.POST['run-id'])

  run = request.rundb.get_run(request.POST['run-id'])
  request.actiondb.stop_run(authenticated_userid(request), run)

  request.session.flash('Stopped run')
  return HTTPFound(location=request.route_url('tests'))

@view_config(route_name='tests_approve', permission='approve_run')
def tests_approve(request):
  username = authenticated_userid(request)
  if not request.rundb.approve_run(request.POST['run-id'], username):
    request.session.flash('Unable to approve run!')
    return HTTPFound(location=request.route_url('tests'))

  run = request.rundb.get_run(request.POST['run-id'])
  request.actiondb.approve_run(username, run)

  request.session.flash('Approved run')
  return HTTPFound(location=request.route_url('tests'))

def purge_run(rundb, run):
  # Remove bad runs
  purged = False
  chi2 = calculate_residuals(run)
  if 'bad_tasks' not in run:
    run['bad_tasks'] = []
  for task in run['tasks']:
    if task['worker_key'] in chi2['bad_users']:
      purged = True
      run['bad_tasks'].append(task)
      if 'stats' in task:
        del task['stats']
      del task['worker_key']

  if purged:
    # Generate new tasks if needed
    run['results_stale'] = True
    results = rundb.get_results(run)
    played_games = results['wins'] + results['losses'] + results['draws']
    if played_games < run['args']['num_games']:
      run['tasks'] += rundb.generate_tasks(run['args']['num_games'] - played_games)

    run['finished'] = False
    if 'sprt' in run['args'] and 'state' in run['args']['sprt']:
      del run['args']['sprt']['state']
    
    rundb.runs.save(run)

  return purged 

@view_config(route_name='tests_purge', permission='approve_run')
def tests_purge(request):
  username = authenticated_userid(request)

  run = request.rundb.get_run(request.POST['run-id'])
  if not run['finished']:
    request.session.flash('Can only purge completed run')
    return HTTPFound(location=request.route_url('tests'))

  purged = purge_run(request.rundb, run)
  if not purged:
    request.session.flash('No bad workers!')
    return HTTPFound(location=request.route_url('tests'))

  request.actiondb.purge_run(username, run)

  request.session.flash('Purged run')
  return HTTPFound(location=request.route_url('tests'))

@view_config(route_name='tests_delete', permission='modify_db')
def tests_delete(request):
  run = request.rundb.get_run(request.POST['run-id'])
  if not can_modify_run(request, run):
    request.session.flash('Unable to modify another users run!')
    return HTTPFound(location=request.route_url('tests'))

  run['deleted'] = True
  run['finished'] = True
  for w in run['tasks']:
    w['pending'] = False
  request.rundb.runs.save(run)

  request.actiondb.delete_run(authenticated_userid(request), run)

  request.session.flash('Deleted run')
  return HTTPFound(location=request.route_url('tests'))

def format_results(run_results, run):
  result = {'style': '', 'info': []}

  # win/loss/draw count
  WLD = [run_results['wins'], run_results['losses'], run_results['draws']]

  if 'spsa' in run['args']:
    result['info'].append('%d/%d iterations' % (run['args']['spsa']['iter'], run['args']['spsa']['num_iter']))
    result['info'].append('%d/%d games played' % (WLD[0] + WLD[1] + WLD[2], run['args']['num_games']))
    return result

  # If the score is 0% or 100% the formulas will crash
  # anyway the statistics are only asymptotic
  if WLD[0] == 0 or WLD[1] == 0:
    result['info'].append('Pending...')
    return result

  state = 'unknown'
  if 'sprt' in run['args']:
    sprt = run['args']['sprt']
    state = sprt.get('state', '')

    stats = stat_util.SPRT(run_results,
                           elo0=sprt['elo0'],
                           alpha=sprt['alpha'],
                           elo1=sprt['elo1'],
                           beta=sprt['beta'],
                           drawelo=sprt['drawelo'])
    result['info'].append('LLR: %.2f (%.2lf,%.2lf) [%.2f,%.2f]' % (stats['llr'], stats['lower_bound'], stats['upper_bound'], sprt['elo0'], sprt['elo1']))
  else:
    elo, elo95, los = stat_util.get_elo(WLD)

    # Display the results
    eloInfo = 'ELO: %.2f +-%.1f (95%%)' % (elo, elo95)
    losInfo = 'LOS: %.1f%%' % (los * 100)

    result['info'].append(eloInfo + ' ' + losInfo)

    if los < 0.05:
      state = 'rejected'
    elif los > 0.95:
      state = 'accepted'

  result['info'].append('Total: %d W: %d L: %d D: %d' % (sum(WLD), WLD[0], WLD[1], WLD[2]))

  if state == 'rejected':
    if WLD[0] > WLD[1]:
      result['style'] = 'yellow'
    else:
      result['style'] = '#FF6A6A'
  elif state == 'accepted':
    result['style'] = '#44EB44'
  return result

def get_worker_key(task):
  if 'worker_info' not in task:
    return '-'
  return '%s-%scores' % (task['worker_info'].get('username', ''), str(task['worker_info']['concurrency']))

def get_chi2(tasks, bad_users):
  """Perform chi^2 test on the stats from each worker"""
  results = {'chi2': 0.0, 'dof': 0, 'p': 0.0, 'residual': {}}

  # Aggregate results by worker
  users = {}
  for task in tasks:
    task['worker_key'] = get_worker_key(task)
    if 'worker_info' not in task:
      continue
    key = get_worker_key(task)
    if key in bad_users:
      continue
    stats = task.get('stats', {})
    wld = [float(stats.get('wins', 0)), float(stats.get('losses', 0)), float(stats.get('draws', 0))]
    if wld == [0.0, 0.0, 0.0]:
      continue
    if key in users:
      for idx in range(len(wld)):
        users[key][idx] += wld[idx]
    else:
      users[key] = wld

  if len(users) == 0:
    return results

  observed = numpy.array(users.values())
  rows,columns = observed.shape
  df = (rows - 1) * (columns - 1)
  column_sums = numpy.sum(observed, axis=0)
  row_sums = numpy.sum(observed, axis=1)
  grand_total = numpy.sum(column_sums)
  if grand_total == 0:
    return results

  expected = numpy.outer(row_sums, column_sums) / grand_total
  diff = observed - expected
  adj = numpy.outer((1 - row_sums / grand_total), (1 - column_sums / grand_total))
  residual = diff / numpy.sqrt(expected * adj)
  for idx in range(len(users)):
    users[users.keys()[idx]] = numpy.max(numpy.abs(residual[idx]))
  chi2 = numpy.sum(diff * diff / expected)
  return {
    'chi2': chi2,
    'dof': df,
    'p': 1 - scipy.stats.chi2.cdf(chi2, df),
    'residual': users,
  }

def calculate_residuals(run):
  bad_users = set()
  chi2 = get_chi2(run['tasks'], bad_users)
  residuals = chi2['residual']

  # Limit bad users to 1 for now
  for _ in range(1):
    worst_user = {}
    for task in run['tasks']:
      if task['worker_key'] in bad_users:
        continue
      task['residual'] = residuals.get(task['worker_key'], 0.0)

      # Special case crashes or time losses
      stats = task.get('stats', {})
      crashes = stats.get('crashes', 0)
      time_losses = stats.get('time_losses', 0)
      if crashes > 1 or time_losses > 1:
        task['residual'] = 8.0

      if abs(task['residual']) < 2.0:
        task['residual_color'] = '#44EB44'
      elif abs(task['residual']) < 2.7:
        task['residual_color'] = 'yellow'
      else:
        task['residual_color'] = '#FF6A6A'

      if chi2['p'] < 0.05 or task['residual'] > 7.0:
        if len(worst_user) == 0 or task['residual'] > worst_user['residual']:
          worst_user['worker_key'] = task['worker_key']
          worst_user['residual'] = task['residual']

    if len(worst_user) == 0:
      break
    bad_users.add(worst_user['worker_key'])
    residuals = get_chi2(run['tasks'], bad_users)['residual']

  chi2['bad_users'] = bad_users
  return chi2

@view_config(route_name='tests_view_spsa_history', renderer='json')
def tests_view_spsa_history(request):
  run = request.rundb.get_run(request.matchdict['id'])
  if 'spsa' not in run['args']:
    return {}

  return run['args']['spsa']

@view_config(route_name='tests_view', renderer='tests_view.mak')
def tests_view(request):
  run = request.rundb.get_run(request.matchdict['id'])
  results = request.rundb.get_results(run)
  run['results_info'] = format_results(results, run)
  run_args = [('id', str(run['_id']), '')]

  for name in ['new_tag', 'new_signature', 'new_options', 'resolved_new',
               'base_tag', 'base_signature', 'base_options', 'resolved_base',
               'sprt', 'num_games', 'spsa', 'tc', 'threads', 'book', 'book_depth',
               'priority', 'username', 'tests_repo', 'info']:

    if not name in run['args']:
      continue

    value = run['args'][name]
    url = ''

    if name == 'new_tag' and 'msg_new' in run['args']:
      value += '  (' + run['args']['msg_new'][:50] + ')'

    if name == 'base_tag' and 'msg_base' in run['args']:
      value += '  (' + run['args']['msg_base'][:50] + ')'

    if name == 'sprt' and value != '-':
      value = 'elo0: %.2f alpha: %.2f elo1: %.2f beta: %.2f state: %s' % \
              (value['elo0'], value['alpha'], value['elo1'], value['beta'], value.get('state', '-'))

    if name == 'spsa' and value != '-':
      params = ['param: %s, best: %.2f, start: %.2f, min: %.2f, max: %.2f, c %f, a %f' % \
                (p['name'], p['theta'], p['start'], p['min'], p['max'], p['c'], p['a']) for p in value['params']]
      value = 'Iter: %d, A: %d, alpha %f, gamma %f\n%s' % (value['iter'], value['A'], value['alpha'], value['gamma'], '\n'.join(params))

    if 'tests_repo' in run['args']:
      if name == 'new_tag':
        url = run['args']['tests_repo'] + '/commit/' + run['args']['resolved_new']
      elif name == 'base_tag':
        url = run['args']['tests_repo'] + '/commit/' + run['args']['resolved_base']
      elif name == 'tests_repo' :
        url = value

    try:
      strval = str(value)
    except:
      strval = value.encode('ascii', 'replace')
    run_args.append((name, strval, url))

  for task in run['tasks']:
    last_updated = task.get('last_updated', datetime.datetime.min)
    task['last_updated'] = delta_date(last_updated)

  return { 'run': run, 'run_args': run_args, 'chi2': calculate_residuals(run)}

def post_result(run):
  title = run['args']['new_tag'][:23]

  if 'username' in run['args']:
    title += '  (' + run['args']['username'] + ')'

  body = 'http://tests.stockfishchess.org/tests/view/%s\n\n' % (str(run['_id']))

  body += run['start_time'].strftime("%d-%m-%y") + ' from '
  body += run['args'].get('username','') + '\n\n'

  body += run['args']['new_tag'] + ': ' + run['args'].get('msg_new', '') + '\n'
  body += run['args']['base_tag'] + ': ' + run['args'].get('msg_base', '') + '\n\n'

  body += 'TC: ' + run['args']['tc'] + ' th ' + str(run['args'].get('threads',1)) + '\n'
  body += '\n'.join(run['results_info']['info']) + '\n\n'

  body += run['args'].get('info', '') + '\n\n'

  msg = MIMEText(body)
  msg['Subject'] = title
  msg['From'] = 'fishtest@noreply.github.com'
  msg['To'] = 'fishcooking_results@googlegroups.com'

  s = smtplib.SMTP('localhost')
  s.sendmail(msg['From'], [msg['To']], msg.as_string())
  s.quit()

@view_config(route_name='tests', renderer='tests.mak')
@view_config(route_name='tests_user', renderer='tests.mak')
def tests(request):
  username = request.matchdict.get('username', '')

  runs = { 'pending':[], 'failed':[], 'active':[], 'finished':[] }

  unfinished_runs = request.rundb.get_unfinished_runs()
  for run in unfinished_runs:
    if len(username) > 0 and run['args'].get('username', '') != username:
      continue

    results = request.rundb.get_results(run)
    run['results_info'] = format_results(results, run)

    state = 'finished'

    for task in run['tasks']:
      if task['active']:
        state = 'active'
      elif task['pending'] and not state == 'active':
        state = 'pending'

    if state == 'finished':
      if not purge_run(request.rundb, run):
        run['finished'] = True
        request.rundb.runs.save(run)
        post_result(run)

    runs[state].append(run)

  runs['pending'].sort(reverse=True, key=lambda run: (-run['args']['priority'], run['start_time']))

  games_per_minute = 0.0
  machines = request.rundb.get_machines()
  for machine in machines:
    machine['last_updated'] = delta_date(machine['last_updated'])
    if machine['nps'] != 0:
      games_per_minute += (machine['nps'] / 1200000.0) * (60.0 / parse_tc(machine['run']['args']['tc'])) * int(machine['concurrency'])
  machines.reverse()

  def remaining_hours(run):
    r = run['results']
    expected_games = run['args']['num_games']
    if 'sprt' in run['args']:
      expected_games = 16000
    remaining_games = max(0, expected_games - r['wins'] - r['losses'] - r['draws'])
    game_secs = parse_tc(run['args']['tc'])
    return game_secs * remaining_games * int(run['args'].get('threads', 1)) / (60*60)

  cores = sum([int(m['concurrency']) for m in machines])
  nps = sum([int(m['concurrency']) * m['nps'] for m in machines])
  if cores > 0:
    pending_hours = 0
    for run in runs['pending'] + runs['active']:
      eta = remaining_hours(run) / cores
      pending_hours += eta
      info = run['results_info']
      if 'Pending...' in info['info']:
        info['info'][0] += ' (%.1f hrs)' % (eta)
        if 'binaries_url' in run:
          info['info'][0] += ' (+bin)'

  else:
    pending_hours = 0

  def total_games(run):
    res = run['results']
    return res['wins'] + res['draws'] + res['losses']
  games_played = sum([total_games(r) for r in runs['finished']])

  # Pagination
  page = max(0, int(request.params.get('page', 1)) - 1)
  page_size = 50
  finished, num_finished = request.rundb.get_finished_runs(skip=page*page_size, limit=page_size, username=username)
  runs['finished'] += finished

  for run in finished:
    results = request.rundb.get_results(run)
    if results['wins'] + results['losses'] + results['draws'] == 0:
      runs['failed'].append(run)

  runs['finished'] = [r for r in runs['finished'] if r not in runs['failed']]

  pages = [{'idx': 'Prev', 'url': '?page=%d' % (page), 'state': 'disabled' if page == 0 else ''}]
  for idx, page_idx in enumerate(range(0, num_finished, page_size)):
    pages.append({'idx': idx + 1, 'url': '?page=%d' % (idx + 1), 'state': 'active' if page == idx else ''})
  pages.append({'idx': 'Next', 'url': '?page=%d' % (page + 2), 'state': 'disabled' if page + 1 == len(pages) - 1 else ''})

  return {
    'runs': runs,
    'finished_runs': num_finished,
    'page_idx': page,
    'pages': pages,
    'machines': machines,
    'show_machines': len(username) == 0,
    'pending_hours': '%.1f' % (pending_hours),
    'games_played': games_played,
    'cores': cores,
    'nps': nps,
    'games_per_minute': int(games_per_minute),
  }
