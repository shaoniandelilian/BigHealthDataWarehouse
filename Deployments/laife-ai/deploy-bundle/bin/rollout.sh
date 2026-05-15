#!/bin/bash
# 用法：rollout.sh <service_name>（对应 systemd unit 的 %i）
# 例：rollout.sh chat | rollout.sh mineru | rollout.sh rag-api
set -e
svc="$1"
if [[ -z "$svc" ]]; then echo "usage: $0 <service>"; exit 2; fi

# 判断属于哪个 repo / unit 模板
case "$svc" in
rag-api|rag-worker)
  repo=/opt/laife/apps/realtime-rag
  unit="laife-rag@${svc#rag-}.service"
  venv=/opt/laife/envs/rag
  ;;
mineru|paddle-ocr|embedding|asr|vllm)
  repo=/opt/laife/apps/laife-ai
  unit="laife-gpu@${svc}.service"
  venv=""
  ;;
*)
  repo=/opt/laife/apps/laife-ai
  unit="laife@${svc}.service"
  venv=""
  ;;
esac

echo ">>> pulling latest code in $repo"
sudo -u laife git -C "$repo" pull

echo ">>> restarting $unit"
sudo systemctl restart "$unit"

echo ">>> waiting 15s then healthcheck"
sleep 15
/opt/laife/bin/healthcheck.sh
