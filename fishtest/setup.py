import os

from setuptools import setup, find_packages

README = ''
CHANGES = ''

requires = [
    'pyramid_mako',
    'pyramid',
    'pyramid_debugtoolbar',
    'pyramid_beaker',
    'waitress',
    'psutil',
    'pymongo',
    'pyzmq',
    ]

setup(name='fishtest',
      version='0.0',
      description='fishtest',
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
      test_suite="fishtest",
      entry_points="""\
      [paste.app_factory]
      main = fishtest:main
      """,
      )
