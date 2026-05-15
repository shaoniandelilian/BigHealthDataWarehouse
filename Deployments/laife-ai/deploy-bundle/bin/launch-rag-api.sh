#!/bin/bash
set -e
cd /opt/laife/apps/realtime-rag
source /opt/laife/envs/rag/bin/activate
exec python3 main.py serve \
  --config configs/pipeline_preset5.yaml \
  --host 0.0.0.0 --port 8011
