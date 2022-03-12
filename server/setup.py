from setuptools import find_packages, setup

README = ""
CHANGES = ""

requires = [
    "pyramid",
    "pyramid_debugtoolbar",
    "pyramid_mako",
    "waitress",
    "pymongo < 4, >= 3.12",
    "numpy",
    "scipy",
    "requests",
    "awscli",
    "zxcvbn",
    "email_validator",
]

setup(
    name="fishtest-server",
    version="0.1",
    description="fishtest-server",
    long_description=README + "\n\n" + CHANGES,
    classifiers=[
        "Programming Language :: Python",
        "Framework :: Pyramid",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Internet :: WWW/HTTP :: WSGI :: Application",
    ],
    author="",
    author_email="",
    url="",
    keywords="web pyramid pylons",
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    install_requires=requires,
    tests_require=requires,
    test_suite="run_all_tests.server_test_suite",
    entry_points={
        "paste.app_factory": [
            "main = fishtest:main",
        ],
    },
)
