#!/bin/bash
set -e
cd /opt/laife/apps/realtime-rag
source /opt/laife/envs/rag/bin/activate
exec python3 main.py worker --config configs/pipeline_preset5.yaml
