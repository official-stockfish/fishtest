#!/bin/sh

# Load the variables with the AWS keys, cron uses a limited environment
source ${HOME}/.bashrc

cd ${HOME}/backup
${HOME}/mongodb/bin/mongodump && \
rm -f dump.tar.gz && \
rm -f dump/fishtest_new/pgns.* && \
tar -czvf dump.tar.gz dump && \
rm -rf dump

date_utc=$(date +%Y%m%d --utc)
mkdir -p archive/${date_utc}
mv dump.tar.gz archive/${date_utc}
s3put -b fishtest -p /home/fishtest/ archive/${date_utc}/dump.tar.gz
# Keep only the latest archive locally, we've filled the HD up multiple times
mv archive/${date_utc}/dump.tar.gz .
