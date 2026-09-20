FROM ubuntu:22.04
ARG FLASH_ARCHIVE=flash-private/FLASH4.8.tar
ENV DEBIAN_FRONTEND=noninteractive
ENV FLASH_HOME=/opt/flash
ENV OMPI_ALLOW_RUN_AS_ROOT=1
ENV OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1
RUN apt-get update && apt-get install -y --no-install-recommends     ca-certificates build-essential gcc g++ gfortran make perl python3 python3-pip     openmpi-bin libopenmpi-dev libhdf5-openmpi-dev libhypre-dev libblas-dev     liblapack-dev libfftw3-dev pkg-config && rm -rf /var/lib/apt/lists/*
COPY ${FLASH_ARCHIVE} /tmp/FLASH4.8.tar
RUN mkdir -p /opt/flash && tar -xf /tmp/FLASH4.8.tar -C /opt/flash --strip-components=1 &&     rm -f /tmp/FLASH4.8.tar && test -x /opt/flash/bin/setup && test -d /opt/flash/source &&     printf '%s\n' '#!/usr/bin/env bash' 'set -euo pipefail'       'setup_name="${1:?FLASH setup name required}"'       'case "$setup_name" in (*..*|/*) echo "invalid setup" >&2; exit 2;; esac'       'shift' 'cd /opt/flash' './setup "$setup_name" -auto "$@"'       'make -C object -j"$(nproc)"' 'cp object/flash4 /workspace/output/flash4'       > /usr/local/bin/scibrain-flash-build && chmod 0555 /usr/local/bin/scibrain-flash-build
RUN python3 -m pip install --no-cache-dir google-cloud-storage
COPY common/scibrain_runner.py /opt/scientificbrain/runner.py
RUN chmod 0555 /opt/scientificbrain/runner.py
ENTRYPOINT ["python3", "/opt/scientificbrain/runner.py"]
