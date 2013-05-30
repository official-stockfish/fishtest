#!/bin/zsh

export CLOP_DIR=~/clop

pkill pserve clop
nohup pserve production.ini >nohup.out &
