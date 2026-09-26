ARG PHYSICSNEMO_VERSION=26.08
FROM nvcr.io/nvidia/physicsnemo/physicsnemo:${PHYSICSNEMO_VERSION}
USER root
RUN python3 -m pip install --no-cache-dir google-cloud-storage && \
    python3 -c "import physicsnemo, torch; from physicsnemo.models.fno.fno import FNO; print('PhysicsNeMo import OK'); print(torch.__version__)"
COPY common/scibrain_runner.py /opt/scientificbrain/runner.py
COPY physicsnemo/scibrain_physicsnemo.py /opt/scientificbrain/physicsnemo_adapter.py
RUN chmod 0555 /opt/scientificbrain/runner.py /opt/scientificbrain/physicsnemo_adapter.py
ENTRYPOINT ["python3", "/opt/scientificbrain/runner.py"]
