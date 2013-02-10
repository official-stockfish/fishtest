#!/bin/bash

LD_LIBRARY_PATH=./cutechess-cli/lib
export LD_LIBRARY_PATH

./cutechess-cli/cutechess-cli -repeat -recover -rounds $1 -resign movecount=3 score=400 -draw movenumber=34 movecount=5 score=20 -concurrency 3 -engine cmd=stockfish proto=uci option.Threads=1 -engine cmd=base proto=uci option.Threads=1 name=base -each tc=$2 book=stockfish_book.bin bookdepth=6 -tournament gauntlet -pgnout results.pgn
