#!/bin/zsh

export CLOP_DIR=~/clop

pkill pserve
#pkill clop
nohup pserve production.ini >nohup.out &
#nohup fishtest/clop.py >clop.out &
