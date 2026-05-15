#!/bin/bash
set -e
cd /opt/laife/apps/laife-ai
source /opt/laife/envs/laife/bin/activate
exec uvicorn main_questionnaire:app --host 0.0.0.0 --port 8015
