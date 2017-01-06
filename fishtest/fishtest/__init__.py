import os, sys
from pyramid.authentication import AuthTktAuthenticationPolicy
from pyramid.authorization import ACLAuthorizationPolicy
from pyramid.config import Configurator
from pyramid.events import NewRequest
from pyramid.session import UnencryptedCookieSessionFactoryConfig

from rundb import RunDb

def main(global_config, **settings):
  """ This function returns a Pyramid WSGI application.
  """
  session_factory = UnencryptedCookieSessionFactoryConfig('fishtest')
  config = Configurator(settings=settings,
                        session_factory=session_factory,
                        root_factory='fishtest.models.RootFactory')

  # Authentication
  with open(os.path.expanduser('~/fishtest.secret'), 'r') as f:
    secret = f.read()
  def groupfinder(username, request):
    return request.userdb.get_user_groups(username)
  config.set_authentication_policy(AuthTktAuthenticationPolicy(secret, callback=groupfinder, hashalg='sha512'))
  config.set_authorization_policy(ACLAuthorizationPolicy())

  rundb = RunDb()
  def add_rundb(event):
    event.request.rundb = rundb
    event.request.userdb = rundb.userdb
    event.request.actiondb = rundb.actiondb
    event.request.regressiondb = rundb.regressiondb
  config.add_subscriber(add_rundb, NewRequest)

  config.add_static_view('css', 'static/css', cache_max_age=3600)
  config.add_static_view('js', 'static/js', cache_max_age=3600)
  config.add_static_view('img', 'static/img', cache_max_age=3600)

  routes = [
  ('home', '/'),
  ('login', '/login'),
  ('signup', '/signup'),
  ('users', '/users'),
  ('actions', '/actions'),
  ('regression', '/regression'),
  ('regression_data', '/regression/data'),
  ('regression_data_json', '/regression/data/json'),
  ('regression_data_save', '/regression/data/save'),
  ('regression_data_delete', '/regression/data/delete'),
  ('tests', '/tests'),
  ('tests_run', '/tests/run'),
  ('tests_modify', '/tests/modify'),
  ('tests_view', '/tests/view/{id}'),
  ('tests_view_spsa_history', '/tests/view/{id}/spsa_history'),
  ('tests_delete', '/tests/delete'),
  ('tests_stop', '/tests/stop'),
  ('tests_approve', '/tests/approve'),
  ('tests_purge', '/tests/purge'),
  ('tests_user', '/tests/user/{username}'),
  ('api_request_task', '/api/request_task'),
  ('api_update_task', '/api/update_task'),
  ('api_failed_task', '/api/failed_task'),
  ('api_stop_run', '/api/stop_run'),
  ('api_request_build', '/api/request_build'),
  ('api_build_ready', '/api/build_ready'),
  ('api_request_version', '/api/request_version'),
  ('api_request_spsa', '/api/request_spsa')
  ]

  for name, route in routes:
    config.add_route(name, route)
    
  config.scan()
  return config.make_wsgi_app()
