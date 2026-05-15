#!/bin/bash
# 遍历所有服务健康检查。退出码：全通=0，任意不通=1
RED="\033[0;31m"; GREEN="\033[0;32m"; NC="\033[0m"
declare -A ENDPOINTS=(
  [8005]="http://127.0.0.1:8005/v1/models"
  [8000]="http://127.0.0.1:8000/docs"
  [8001]="http://127.0.0.1:8001/"
  [8003]="http://127.0.0.1:8003/docs"
  [8012]="http://127.0.0.1:8012/health"
  [8002]="http://127.0.0.1:8002/health"
  [8010]="http://127.0.0.1:8010/docs"
  [8013]="http://127.0.0.1:8013/health"
  [8014]="http://127.0.0.1:8014/docs"
  [8015]="http://127.0.0.1:8015/docs"
  [8011]="http://127.0.0.1:8011/metrics"
)
fail=0
for port in 8005 8000 8001 8003 8012 8002 8010 8013 8014 8015 8011; do
  url="${ENDPOINTS[$port]}"
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$url" 2>/dev/null || echo "---")
  if [[ "$code" == "200" ]]; then
    echo -e "${GREEN}PASS${NC} $port  ($url → $code)"
  else
    echo -e "${RED}FAIL${NC} $port  ($url → $code)"
    fail=1
  fi
done
exit $fail
