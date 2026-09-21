ARG CUDA_IMAGE=nvidia/cuda:12.8.1-devel-ubuntu24.04
FROM ${CUDA_IMAGE}

ARG WARPX_VERSION=26.09
ARG CUDA_ARCHS="80;89"

ENV DEBIAN_FRONTEND=noninteractive
ENV PATH=/opt/warpx/bin:${PATH}
ENV OMPI_ALLOW_RUN_AS_ROOT=1
ENV OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates git cmake ninja-build build-essential \
    python3 python3-pip python3-venv \
    openmpi-bin libopenmpi-dev \
    libfftw3-dev libfftw3-mpi-dev \
    libhdf5-openmpi-dev libboost-all-dev \
    libblas-dev liblapack-dev \
    libblaspp-dev liblapackpp-dev \
    pkg-config \
 && rm -rf /var/lib/apt/lists/*

RUN git clone --branch "${WARPX_VERSION}" --depth 1 --recursive \
      https://github.com/BLAST-WarpX/warpx.git /src/warpx \
 && cmake -S /src/warpx -B /src/warpx/build -GNinja \
      -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_INSTALL_PREFIX=/opt/warpx \
      -DCMAKE_CUDA_ARCHITECTURES="${CUDA_ARCHS}" \
      -DWarpX_COMPUTE=CUDA \
      -DWarpX_DIMS="1;2;3;RZ" \
      -DWarpX_MPI=ON \
      -DWarpX_OPENPMD=ON \
      -DWarpX_FFT=ON \
      -DWarpX_QED=OFF \
      -DWarpX_PYTHON=OFF \
 && cmake --build /src/warpx/build --parallel "$(nproc)" \
 && cmake --install /src/warpx/build \
 && rm -rf /src/warpx

WORKDIR /workspace
