#!/bin/zsh

pkill pserve
nohup pserve production.ini >nohup.out &
