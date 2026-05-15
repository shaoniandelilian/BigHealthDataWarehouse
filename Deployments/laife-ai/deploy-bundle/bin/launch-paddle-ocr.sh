#!/bin/bash
set -e
cd /opt/laife/apps/laife-ai
source /opt/laife/envs/paddle/bin/activate
exec python3 OCR/paddle-ocr.py
