#!/usr/bin/python

from setuptools import find_packages, setup

requires = ["requests"]

setup(
    name="fishtest_worker",
    version="0.1",
    packages=find_packages(),
    install_requires=requires,
    test_suite="test_worker",
)
