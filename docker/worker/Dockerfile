FROM ubuntu:23.10

RUN apt update && apt upgrade -y && apt install -y \
  git vim python3 python3-distutils make g++ # clang llvm

RUN useradd --create-home --shell /bin/bash worker

WORKDIR /home/worker
COPY run_workers.sh .
RUN chmod +x run_workers.sh

USER worker
ENV NUM_WORKERS ${NUM_WORKERS}
ENV WORKER_ARGS ${WORKER_ARGS}

CMD ./run_workers.sh
