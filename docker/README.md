docker containers for fishtest server (TODO) and workers

## Setup

Copy the example .env and change the values for NUM_WORKERS and WORKER_ARGS.

```bash
cp .env.example .env
```

## local worker

Example of starting a single fishtest worker locally

```bash
docker compose up --build
```

_If you want to start the container in the background run_.  
 `docker compose up --build -d`

## remote workers

Example of starting fishtest workers on a few remote servers:

```bash
REMOTE_SERVERS=(
  server1
  server2
  server3
)

cd worker
for server in ${REMOTE_SERVERS[@]}; do
  echo $server
  docker -H ssh://$server compose up --build -d
done
```
