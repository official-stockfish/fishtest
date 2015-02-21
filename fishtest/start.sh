#!/bin/zsh

cd /home/fishtest/fishtest/fishtest

pkill -f pserve
nohup pserve --monitor-restart production.ini >nohup.out &
