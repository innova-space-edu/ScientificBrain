FROM ubuntu:24.04
ARG GEANT4_VERSION=11.4.2
ENV DEBIAN_FRONTEND=noninteractive
ENV PATH=/opt/geant4/bin:${PATH}
ENV LD_LIBRARY_PATH=/opt/geant4/lib:${LD_LIBRARY_PATH}
RUN apt-get update && apt-get install -y --no-install-recommends     ca-certificates git build-essential cmake ninja-build python3 python3-pip     libexpat1-dev libxerces-c-dev libgl1-mesa-dev libglu1-mesa-dev && rm -rf /var/lib/apt/lists/*
RUN git clone --branch "v${GEANT4_VERSION}" --depth 1 https://github.com/Geant4/geant4.git /src/geant4 &&     cmake -S /src/geant4 -B /src/geant4/build -GNinja       -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/opt/geant4       -DGEANT4_INSTALL_DATA=ON -DGEANT4_USE_GDML=ON -DGEANT4_BUILD_MULTITHREADED=ON       -DGEANT4_USE_QT=OFF -DGEANT4_USE_OPENGL_X11=OFF &&     cmake --build /src/geant4/build --parallel "$(nproc)" && cmake --install /src/geant4/build &&     cmake -S /src/geant4/examples/basic/B1 -B /opt/geant4-smoke -GNinja -DCMAKE_PREFIX_PATH=/opt/geant4 &&     cmake --build /opt/geant4-smoke --parallel "$(nproc)" && cp /src/geant4/examples/basic/B1/*.mac /opt/geant4-smoke/ && rm -rf /src/geant4
RUN python3 -m pip install --break-system-packages --no-cache-dir google-cloud-storage
COPY common/scibrain_runner.py /opt/scientificbrain/runner.py
RUN chmod 0555 /opt/scientificbrain/runner.py && test -x /opt/geant4-smoke/exampleB1
ENTRYPOINT ["python3", "/opt/scientificbrain/runner.py"]
