#!/bin/sh
# Backup MongoDB to AWS S3
# https://docs.aws.amazon.com/cli/latest/topic/s3-config.html
# List available backups with:
# ${VENV}/bin/aws s3 ls s3://fishtest/backup/archive/
# Download a backup with:
# ${VENV}/bin/aws s3 cp s3://fishtest/backup/archive/<YYYYMMDD>/dump.tar dump.tar

# Load the variables with the AWS keys, cron uses a limited environment
. ${HOME}/.profile

cd ${HOME}/backup
for db_name in "fishtest_new" "admin" "config" "local"; do
  mongodump --db=${db_name} --numParallelCollections=1 --excludeCollection="pgns" --gzip
done
tar -cvf dump.tar dump
rm -rf dump

date_utc=$(date +%Y%m%d --utc)
${VENV}/bin/aws configure set default.s3.max_concurrent_requests 1
${VENV}/bin/aws s3 cp dump.tar s3://fishtest/backup/archive/${date_utc}/dump.tar
