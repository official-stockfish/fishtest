#!/bin/sh

#nohup stdbuf -oL pserve development.ini --reload > nohup.out 2>&1 &
pserve development.ini --reload
