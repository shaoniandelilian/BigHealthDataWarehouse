#!/bin/bash
set -e
cd /opt/laife/apps/laife-ai/OCR
source /opt/laife/envs/ocr/bin/activate
exec uvicorn main:app --host 0.0.0.0 --port 8002
