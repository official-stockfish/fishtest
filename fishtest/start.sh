#!/bin/zsh

export CLOP_DIR=~/clop

pkill pserve
pkill clop
nohup pserve production.ini >nohup.out &
