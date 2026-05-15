#!/bin/bash
set -e
cd /opt/laife/apps/laife-ai
source /opt/laife/envs/laife/bin/activate
exec uvicorn main_report:app --host 0.0.0.0 --port 8013
