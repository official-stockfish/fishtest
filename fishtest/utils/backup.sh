#!/bin/sh
# Backup MongoDB to AWS S3, download a backup with:
# ${VENV}/bin/fetch_file s3://fishtest/backup/archive/<YYYYMMDD>/dump.tar.gz -o dump.tar.gz

# Load the variables with the AWS keys, cron uses a limited environment
. ${HOME}/.profile

cd ${HOME}/backup
mongodump && \
rm -f dump.tar.gz && \
: > dump/fishtest_new/pgns.bson && \
tar -czvf dump.tar.gz dump && \
rm -rf dump

date_utc=$(date +%Y%m%d --utc)
mkdir -p archive/${date_utc}
mv dump.tar.gz archive/${date_utc}
${VENV}/bin/s3put -b fishtest -p ${HOME} archive/${date_utc}/dump.tar.gz
# Keep only the latest archive locally
mv archive/${date_utc}/dump.tar.gz .
