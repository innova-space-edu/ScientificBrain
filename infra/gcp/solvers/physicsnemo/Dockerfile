ARG PHYSICSNEMO_VERSION=26.08
FROM nvcr.io/nvidia/physicsnemo/physicsnemo:${PHYSICSNEMO_VERSION}

USER root
RUN python3 -m pip install --no-cache-dir google-cloud-storage \
 && python3 -c "import importlib.util; spec=importlib.util.find_spec('physicsnemo'); assert spec is not None, 'physicsnemo module missing'; print('PhysicsNeMo module', spec.origin)"

COPY common/scibrain_runner.py /opt/scientificbrain/runner.py
COPY physicsnemo/scibrain_physicsnemo.py /opt/scientificbrain/physicsnemo_adapter.py
RUN chmod 0555 /opt/scientificbrain/runner.py /opt/scientificbrain/physicsnemo_adapter.py \
 && python3 -m py_compile /opt/scientificbrain/runner.py /opt/scientificbrain/physicsnemo_adapter.py

ENTRYPOINT ["python3", "/opt/scientificbrain/runner.py"]
