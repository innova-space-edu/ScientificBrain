#!/usr/bin/env python3
import argparse, json
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument("--project",required=True); p.add_argument("--region",default="us-central1")
p.add_argument("--repository",default="scientificbrain-solvers")
p.add_argument("--manifest",default=str(Path(__file__).with_name("solver-images.json")))
a=p.parse_args()
data=json.loads(Path(a.manifest).read_text())
profiles={}
for solver,spec in data.items():
    profile={"image_uri":f"{a.region}-docker.pkg.dev/{a.project}/{a.repository}/{solver}:{spec['tag']}","machine_type":spec["batch_machine_type"],"max_retry_count":1}
    if spec.get("gpu_type"):
        profile.update({"gpu_type":spec["gpu_type"],"max_gpus_per_node":spec["max_gpus_per_node"],"install_gpu_drivers":True})
    profiles[solver]=profile
print(json.dumps(profiles,separators=(",",":"),sort_keys=True))
