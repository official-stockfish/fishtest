#!/usr/bin/python

from setuptools import setup, find_packages

setup(
    name = "fishtest_worker",
    version = "0.1",
    packages = find_packages(),
    test_suite = "test_worker"
)
