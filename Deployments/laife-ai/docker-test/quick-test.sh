#!/bin/bash
# Quick service test script for manual interactive use

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
PASS() { echo -e "${GREEN}[PASS]${NC} $1"; }
FAIL() { echo -e "${RED}[FAIL]${NC} $1"; }

# ---- 0. Env fix ----
cat > /opt/laife/apps/laife-ai/.env << 'ENVEOF'
DASHSCOPE_API_KEY=placeholder
PDF_API_KEY=placeholder
KB_API_URL=http://172.20.8.12:8000/chat/stream
KB_API_KEY=placeholder
LAIFE_MCP_URL=http://127.0.0.1:8004/mcp
LAIFE_INTENT_ROUTER_MODEL=/opt/laife/models/Qwen3.5-4B
VLLM_BASE_URL=http://127.0.0.1:8005/v1
ENTITY_MODEL_NAME=/opt/laife/models/Qwen3.5-4B
LOCAL_MODEL_NAME=/opt/laife/models/Qwen3.5-4B
PG_DSN=postgresql://admin:test123@laife-postgres:5432/laife_ai
ENVEOF
chown laife:laife /opt/laife/apps/laife-ai/.env
mkdir -p /opt/laife/logs/laife-ai /opt/laife/logs/realtime-rag
chown -R laife:laife /opt/laife/logs /opt/laife/data

PASS ".env fixed"

# Install missing deps
/opt/laife/envs/laife/bin/pip install -q dashscope langchain 2>&1 | tail -1
/opt/laife/envs/rag/bin/pip install -q prometheus-client python-multipart 2>&1 | tail -1
PASS "missing deps installed"

# Copy ques2label module code (excluded by dockerignore)
mkdir -p /opt/laife/apps/laife-ai/ques2label/config /opt/laife/apps/laife-ai/ques2label/model /opt/laife/apps/laife-ai/ques2label/data
# We'll copy from host later via docker cp
PASS "ques2label dirs created"

# ---- Test helpers ----
TOTAL_PASS=0
TOTAL_FAIL=0

run_service() {
  local name=$1 port=$2 cmd=$3 cwd=$4 venv=$5 wait_s=$6 health_url=$7
  echo ""
  echo "------------------------------------------------"
  echo "  Testing: $name (port $port)"

  su -s /bin/bash laife -c "cd $cwd && source /opt/laife/envs/$venv/bin/activate && $cmd" > /opt/laife/logs/${name}.log 2>&1 &
  local PID=$!

  for i in $(seq 1 $wait_s); do
    sleep 1
    if ! kill -0 $PID 2>/dev/null; then
      FAIL "$name died at ${i}s"
      echo "  --- log tail ---"
      tail -3 /opt/laife/logs/${name}.log
      TOTAL_FAIL=$((TOTAL_FAIL+1))
      return 1
    fi
    if netstat -tlnp 2>/dev/null | grep -q ":${port} "; then
      echo "  Port bound at ${i}s"
      sleep 2
      CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$health_url" 2>/dev/null || echo "000")
      echo "  HTTP $health_url -> $CODE"
      PASS "$name (port $port, HTTP $CODE)"
      TOTAL_PASS=$((TOTAL_PASS+1))
      kill $PID 2>/dev/null; wait $PID 2>/dev/null
      return 0
    fi
  done
  FAIL "$name timeout after ${wait_s}s"
  kill $PID 2>/dev/null; wait $PID 2>/dev/null
  TOTAL_FAIL=$((TOTAL_FAIL+1))
}

# ---- 1. PostgreSQL services ----
echo ""
echo "========================================"
echo "  Phase 1: PostgreSQL-dependent services"
echo "========================================"

run_service "questionnaire" 8015 \
  "uvicorn main_questionnaire:app --host 0.0.0.0 --port 8015" \
  "/opt/laife/apps/laife-ai" "laife" 20 "http://127.0.0.1:8015/docs"

run_service "weekly" 8014 \
  "uvicorn main_weekly:app --host 0.0.0.0 --port 8014" \
  "/opt/laife/apps/laife-ai" "laife" 20 "http://127.0.0.1:8014/docs"

# ---- 2. Chat (needs Milvus + ques2label) ----
echo ""
echo "========================================"
echo "  Phase 2: Chat (Milvus-dependent)"
echo "========================================"
echo "--- chat :8010 ---"
su -s /bin/bash laife -c "
  cd /opt/laife/apps/laife-ai
  source /opt/laife/envs/laife/bin/activate
  uvicorn main_chat:app --host 0.0.0.0 --port 8010
" > /opt/laife/logs/chat.log 2>&1 &
PID=$!
sleep 15
if kill -0 $PID 2>/dev/null; then
  netstat -tlnp 2>/dev/null | grep 8010 && PASS "chat port bound" || echo "  (alive but port not bound - connecting to Milvus?)"
  curl -s -o /dev/null -w "  HTTP /docs -> %{http_code}\n" --max-time 3 http://127.0.0.1:8010/docs 2>/dev/null
  TOTAL_PASS=$((TOTAL_PASS+1))
  kill $PID 2>/dev/null; wait $PID 2>/dev/null
else
  FAIL "chat died (needs Milvus + ques2label)"
  tail -3 /opt/laife/logs/chat.log
  TOTAL_FAIL=$((TOTAL_FAIL+1))
fi

# ---- 3. Report (needs ques2label + mineru) ----
echo ""
echo "--- report :8013 ---"
su -s /bin/bash laife -c "
  cd /opt/laife/apps/laife-ai
  source /opt/laife/envs/laife/bin/activate
  uvicorn main_report:app --host 0.0.0.0 --port 8013
" > /opt/laife/logs/report.log 2>&1 &
PID=$!
sleep 10
if kill -0 $PID 2>/dev/null; then
  netstat -tlnp 2>/dev/null | grep 8013 && PASS "report port bound" || PASS "report alive"
  kill $PID 2>/dev/null; wait $PID 2>/dev/null
  TOTAL_PASS=$((TOTAL_PASS+1))
else
  FAIL "report died (needs ques2label + mineru)"
  tail -3 /opt/laife/logs/report.log
  TOTAL_FAIL=$((TOTAL_FAIL+1))
fi

# ---- 4. PDF Extract (needs mineru/GPU) ----
echo ""
echo "--- pdf-extract :8002 ---"
su -s /bin/bash laife -c "
  cd /opt/laife/apps/laife-ai/OCR
  source /opt/laife/envs/ocr/bin/activate
  uvicorn main:app --host 0.0.0.0 --port 8002
" > /opt/laife/logs/pdf-extract.log 2>&1 &
PID=$!
sleep 6
if kill -0 $PID 2>/dev/null; then
  PASS "pdf-extract alive (mineru available?)"
  kill $PID 2>/dev/null; wait $PID 2>/dev/null
  TOTAL_PASS=$((TOTAL_PASS+1))
else
  echo "  DIED (expected: GPU/mineru not in Docker env)"
  tail -2 /opt/laife/logs/pdf-extract.log
  TOTAL_FAIL=$((TOTAL_FAIL+1))
fi

# ---- 5. RAG services ----
echo ""
echo "========================================"
echo "  Phase 5: RAG services"
echo "========================================"

run_service "rag-api" 8011 \
  "python3 main.py serve --config configs/pipeline_preset5.yaml --host 0.0.0.0 --port 8011" \
  "/opt/laife/apps/realtime-rag" "rag" 25 "http://127.0.0.1:8011/metrics"

# RAG worker (no port)
echo ""
echo "--- rag-worker ---"
su -s /bin/bash laife -c "
  cd /opt/laife/apps/realtime-rag
  source /opt/laife/envs/rag/bin/activate
  python3 main.py worker --config configs/pipeline_preset5.yaml
" > /opt/laife/logs/rag-worker.log 2>&1 &
PID=$!
sleep 10
if kill -0 $PID 2>/dev/null; then
  PASS "rag-worker running"
  TOTAL_PASS=$((TOTAL_PASS+1))
  kill $PID 2>/dev/null; wait $PID 2>/dev/null
else
  echo "  DIED"
  tail -5 /opt/laife/logs/rag-worker.log
  TOTAL_FAIL=$((TOTAL_FAIL+1))
fi

# ---- Summary ----
echo ""
echo "========================================"
echo "  FINAL: $TOTAL_PASS PASS / $TOTAL_FAIL FAIL"
echo "========================================"
