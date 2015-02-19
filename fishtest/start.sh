#!/bin/zsh

cd /home/fishtest/fishtest/fishtest

pkill pserve
nohup pserve --monitor-restart production.ini >nohup.out &
