FROM ubuntu:22.04
ARG PETSC_VERSION=3.14.6
ARG EDIPIC2D_REF=a32863ad046eabe170037e9ef3b849b763d25053
ENV DEBIAN_FRONTEND=noninteractive
ENV PETSC_DIR=/opt/petsc
ENV LD_LIBRARY_PATH=/opt/petsc/lib:${LD_LIBRARY_PATH}
ENV PATH=/opt/edipic/bin:${PATH}
ENV OMPI_ALLOW_RUN_AS_ROOT=1
ENV OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1
RUN apt-get update && apt-get install -y --no-install-recommends     ca-certificates git build-essential gcc g++ gfortran make python3 python3-pip     openmpi-bin libopenmpi-dev libblas-dev liblapack-dev pkg-config && rm -rf /var/lib/apt/lists/*
RUN git clone --branch "v${PETSC_VERSION}" --depth 1 https://gitlab.com/petsc/petsc.git /src/petsc &&     cd /src/petsc && ./configure --with-cc=mpicc --with-cxx=mpicxx --with-fc=mpif90       --with-debugging=0 COPTFLAGS='-O2' CXXOPTFLAGS='-O2' FOPTFLAGS='-O2'       --download-hypre --download-f2cblaslapack --prefix=/opt/petsc PETSC_ARCH=linux-gnu-opt PETSC_DIR=/src/petsc &&     make PETSC_DIR=/src/petsc PETSC_ARCH=linux-gnu-opt -j"$(nproc)" all &&     make PETSC_DIR=/src/petsc PETSC_ARCH=linux-gnu-opt install && rm -rf /src/petsc
RUN git clone https://github.com/PrincetonUniversity/EDIPIC-2D.git /src/edipic2d &&     cd /src/edipic2d && git checkout "${EDIPIC2D_REF}" && cd src && make -j"$(nproc)" &&     mkdir -p /opt/edipic/bin && cp edipic2d /opt/edipic/bin/edipic2d && ldd /opt/edipic/bin/edipic2d && rm -rf /src/edipic2d
RUN python3 -m pip install --no-cache-dir google-cloud-storage
COPY common/scibrain_runner.py /opt/scientificbrain/runner.py
RUN chmod 0555 /opt/scientificbrain/runner.py
ENTRYPOINT ["python3", "/opt/scientificbrain/runner.py"]
