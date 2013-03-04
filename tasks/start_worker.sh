#!/bin/sh

nohup python worker.py --host 54.235.120.254 --concurrency 3 "$FISHTEST_USER" "$FISHTEST_PASSWORD" &
