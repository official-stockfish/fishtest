import os

from setuptools import setup, find_packages

README = ''
CHANGES = ''

requires = [
    'pyramid',
    'pyramid_debugtoolbar',
    'waitress',
    'psutil',
    'pymongo',
    'pyzmq',
    'scipy',
    'requests'
    ]

setup(name='fishtest-server',
      version='0.1',
      description='fishtest-server',
      long_description=README + '\n\n' + CHANGES,
      classifiers=[
        "Programming Language :: Python",
        "Framework :: Pyramid",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Internet :: WWW/HTTP :: WSGI :: Application",
        ],
      author='',
      author_email='',
      url='',
      keywords='web pyramid pylons',
      packages=find_packages(),
      include_package_data=True,
      zip_safe=False,
      install_requires=requires,
      tests_require=requires,
      test_suite="test_server",
      entry_points="""\
      [paste.app_factory]
      main = fishtest:main
      """,
      )
