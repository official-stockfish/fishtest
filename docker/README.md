docker containers for fishtest server (TODO) and workers


### local worker

Example of starting a single fishtest worker locally

```bash
NUM_WORKERS=1 WORKER_ARGS="username password" docker compose up --build -d
```

### remote workers

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
  NUM_WORKERS=2 WORKER_ARGS="username password --concurrency 2" \
    docker -H ssh://$server compose up --build -d
done
```
