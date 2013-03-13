#!/bin/sh

cd worker

python worker.py --concurrency 3 "$FISHTEST_USER" "$FISHTEST_PASSWORD" "$FISHTEST_DIR"

