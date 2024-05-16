from setuptools import find_packages, setup

README = ""
CHANGES = ""

requires = [
    "pyramid",
    "pyramid_debugtoolbar",
    "pyramid_mako",
    "waitress",
    "pymongo",
    "numpy",
    "scipy",
    "requests",
    "awscli",
    "zxcvbn",
    "email_validator",
    "vtjson",
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
    entry_points={
        "paste.app_factory": [
            "main = fishtest:main",
        ],
    },
)
