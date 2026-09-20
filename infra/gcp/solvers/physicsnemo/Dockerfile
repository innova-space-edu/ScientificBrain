ARG PHYSICSNEMO_VERSION=26.08
FROM nvcr.io/nvidia/physicsnemo/physicsnemo:${PHYSICSNEMO_VERSION}
USER root
RUN python3 -m pip install --no-cache-dir google-cloud-storage &&     python3 -c "import physicsnemo, torch; print('PhysicsNeMo import OK'); print(torch.__version__)"
COPY common/scibrain_runner.py /opt/scientificbrain/runner.py
RUN chmod 0555 /opt/scientificbrain/runner.py
ENTRYPOINT ["python3", "/opt/scientificbrain/runner.py"]
