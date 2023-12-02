#!/bin/bash

git clone \
  https://github.com/official-stockfish/fishtest \
  ~/fishtest

for worker in $(seq 1 $NUM_WORKERS); do
  worker_dir=~/worker$worker
  cp -r fishtest $worker_dir
  cd $worker_dir/worker
  python3 worker.py $WORKER_ARGS &
  cd ~
done

wait
