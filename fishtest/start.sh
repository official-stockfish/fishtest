#!/bin/sh

pkill -f pserve

cd /home/fishtest/fishtest/fishtest
nohup stdbuf -oL pserve --monitor-restart production.ini >nohup.out &
