#!/bin/bash
set -e
cd /opt/laife/apps/laife-ai
export HF_HOME=/opt/laife/data/ocr-cache/huggingface
export MODELSCOPE_CACHE=/opt/laife/data/ocr-cache/modelscope
source /opt/laife/envs/ocr/bin/activate
exec uvicorn OCR.mineru_api:app --host 0.0.0.0 --port 8000
