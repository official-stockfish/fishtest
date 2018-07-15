#!/bin/sh

# Load the AWS variables when scheduled with cron
source ~/.bashrc

cd ~/backup
~/mongodb/bin/mongodump && \
rm -f dump.tar.gz && \
rm -f dump/fishtest_new/pgns.* && \
tar -czvf dump.tar.gz dump && \
rm -rf dump

DAY=$(date +%Y%m%d --utc -d '1 hour')
mkdir -p archive/$DAY
mv dump.tar.gz archive/$DAY
s3put -b fishtest -p /home/fishtest/ archive/$DAY/dump.tar.gz
# Keep only the latest archive locally, we've filled the HD up multiple times
mv archive/$DAY/dump.tar.gz .
