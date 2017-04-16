#!/bin/sh

pkill -f pserve

cd /home/fishtest/fishtest/fishtest
nohup stdbuf -oL pserve production.ini >nohup.out &
