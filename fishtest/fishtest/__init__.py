import os, sys
from pyramid.config import Configurator
from pyramid.events import NewRequest
from pyramid.session import UnencryptedCookieSessionFactoryConfig

# For rundb
sys.path.append(os.path.expanduser('~/fishtest'))
from tasks.rundb import RunDb

def main(global_config, **settings):
  """ This function returns a Pyramid WSGI application.
  """
  session_factory = UnencryptedCookieSessionFactoryConfig('fishtest')
  config = Configurator(settings=settings, session_factory=session_factory)

  rundb = RunDb()
  def add_rundb(event):
    event.request.rundb = rundb
  config.add_subscriber(add_rundb, NewRequest)

  config.add_static_view('css', 'static/css', cache_max_age=3600)
  config.add_static_view('js', 'static/js', cache_max_age=3600)
  config.add_static_view('img', 'static/img', cache_max_age=3600)
  config.add_route('home', '/')
  config.add_route('tests', '/tests')
  config.add_route('tests_run', '/tests/run')
  config.scan()
  return config.make_wsgi_app()
