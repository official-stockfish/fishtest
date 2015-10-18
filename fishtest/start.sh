#!/bin/zsh

pkill -f start_fishtest
pkill -f pserve

cd /home/fishtest/fishtest/fishtest
nohup pserve --monitor-restart production.ini >nohup.out &
