ARG CUDA_IMAGE=nvidia/cuda:12.4.1-devel-ubuntu22.04
FROM ${CUDA_IMAGE}
ARG PICONGPU_VERSION=0.8.0
ARG OPENPMD_VERSION=0.15.2
ARG CUDA_ARCH=89
ENV DEBIAN_FRONTEND=noninteractive
ENV PICSRC=/opt/picongpu
ENV PIC_EXAMPLES=/opt/picongpu/share/picongpu/examples
ENV PATH=/opt/picongpu:/opt/picongpu/bin:/opt/picongpu/src/tools/bin:/opt/openpmd/bin:${PATH}
ENV PYTHONPATH=/opt/picongpu/lib/python:${PYTHONPATH}
ENV CMAKE_PREFIX_PATH=/opt/openpmd:${CMAKE_PREFIX_PATH}
ENV LD_LIBRARY_PATH=/opt/openpmd/lib:${LD_LIBRARY_PATH}
ENV OMPI_ALLOW_RUN_AS_ROOT=1
ENV OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1
ENV SCIBRAIN_PICONGPU_CUDA_ARCH=${CUDA_ARCH}
RUN apt-get update && apt-get install -y --no-install-recommends     ca-certificates git rsync build-essential gcc g++ gfortran cmake ninja-build     python3 python3-pip openmpi-bin libopenmpi-dev libboost-all-dev libpng-dev     libhdf5-openmpi-dev libfftw3-dev pkg-config nlohmann-json3-dev && rm -rf /var/lib/apt/lists/*
RUN git clone --branch "${OPENPMD_VERSION}" --depth 1 https://github.com/openPMD/openPMD-api.git /src/openpmd &&     cmake -S /src/openpmd -B /src/openpmd/build -GNinja       -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/opt/openpmd       -DopenPMD_USE_MPI=ON -DopenPMD_USE_HDF5=ON -DopenPMD_USE_ADIOS2=OFF -DopenPMD_USE_PYTHON=OFF &&     cmake --build /src/openpmd/build --parallel "$(nproc)" && cmake --install /src/openpmd/build && rm -rf /src/openpmd
RUN git clone --branch "${PICONGPU_VERSION}" --depth 1 --recursive https://github.com/ComputationalRadiationPhysics/picongpu.git /opt/picongpu &&     pic-create "${PIC_EXAMPLES}/LaserWakefield" /opt/picongpu-smoke &&     cd /opt/picongpu-smoke && pic-build -b "cuda:${CUDA_ARCH}" && test -x /opt/picongpu-smoke/.build/picongpu
RUN python3 -m pip install --no-cache-dir google-cloud-storage
COPY common/scibrain_runner.py /opt/scientificbrain/runner.py
RUN chmod 0555 /opt/scientificbrain/runner.py
ENTRYPOINT ["python3", "/opt/scientificbrain/runner.py"]
