#!/bin/zsh

export CLOP_DIR=~/clop

pkill pserve
nohup pserve production.ini >nohup.out &
