#!/bin/sh

pkill -f pserve

nohup stdbuf -oL pserve --monitor-restart production.ini > nohup.out &
