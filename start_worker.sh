#!/bin/sh

export FISHTEST_HOST=54.235.120.254
nohup celery worker --app=tasks -Q games -c 1 &
