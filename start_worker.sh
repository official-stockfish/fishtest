#!/bin/sh

nohup celery worker --app=tasks -Q games -c 1 &
