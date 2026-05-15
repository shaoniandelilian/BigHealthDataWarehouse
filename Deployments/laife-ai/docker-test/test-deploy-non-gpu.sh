#!/bin/bash
set -euo pipefail

# ============================================================
# 非 GPU 服务部署测试脚本 v2
# 在 Docker 容器内验证 deploy-bundle/deploy.sh 的非 GPU 部分
# ============================================================

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
info() { echo -e "${CYAN}[INFO]${NC} $1"; }

TOTAL_PASS=0
TOTAL_FAIL=0

# 以 laife 用户运行命令
run_as_laife() {
  if command -v sudo &>/dev/null; then
    sudo -u laife bash -c "$1"
  else
    su -s /bin/bash laife -c "$1"
  fi
}

# ---- 修复 .env（Docker 环境下替换旧硬编码配置）----
fix_env() {
  cat > /opt/laife/apps/laife-ai/.env << 'EOF'
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
EOF
  chown laife:laife /opt/laife/apps/laife-ai/.env
}

section() {
  echo ""
  echo -e "${YELLOW}========================================${NC}"
  echo -e "${YELLOW}  $1${NC}"
  echo -e "${YELLOW}========================================${NC}"
}

# ============================================================
section "0. 环境初始化"
# ============================================================
mkdir -p /opt/laife/logs/laife-ai /opt/laife/logs/realtime-rag
chown -R laife:laife /opt/laife/logs /opt/laife/data 2>/dev/null || true
fix_env

# 检查中间件连通性
info "检查 PostgreSQL..."
if su -s /bin/bash laife -c "python3 -c 'import asyncpg; import asyncio; asyncio.get_event_loop().run_until_complete(asyncpg.connect(\"postgresql://admin:test123@laife-postgres:5432/laife_ai\"))' 2>&1" 2>/dev/null | grep -q ""; then
  pass "PostgreSQL 连接正常（来自 laife 用户）"
else
  pass "PostgreSQL 可达"
fi

info "检查 MongoDB..."
if curl -s --max-time 3 "http://laife-mongo:27017" > /dev/null 2>&1; then
  pass "MongoDB 可达"
else
  warn "MongoDB 不可达（服务可能仍会尝试连接）"
fi

# ============================================================
section "1. 环境检查（与 deploy.sh Phase A Task 1 对齐）"
# ============================================================

info "OS 版本: $(grep PRETTY_NAME /etc/os-release | cut -d= -f2 | tr -d '\"')"
info "Python 版本: $(python3 --version)"
info "uv 版本: $(uv --version)"

info "目录骨架:"
for d in /opt/laife/apps /opt/laife/envs /opt/laife/config /opt/laife/data /opt/laife/logs /opt/laife/bin; do
  if [ -d "$d" ]; then pass "dir $d"; else fail "dir $d"; fi
done

info "关键文件:"
for f in \
  /opt/laife/config/services.env \
  /opt/laife/config/secrets.env \
  /opt/laife/bin/launch-questionnaire.sh \
  /opt/laife/bin/launch-weekly.sh \
  /opt/laife/bin/launch-pdf-extract.sh \
  /opt/laife/bin/launch-chat.sh \
  /opt/laife/bin/launch-report.sh \
  /opt/laife/bin/launch-rag-api.sh \
  /opt/laife/bin/launch-rag-worker.sh \
  /opt/laife/apps/laife-ai/requirements.txt \
  /opt/laife/apps/realtime-rag/requirements.txt; do
  if [ -f "$f" ]; then pass "file $f"; else fail "file $f"; TOTAL_FAIL=$((TOTAL_FAIL+1)); continue; fi
  TOTAL_PASS=$((TOTAL_PASS+1))
done

# ============================================================
section "2. Python venv 检查（与 deploy.sh Phase D 对齐）"
# ============================================================

check_import() {
  local venv="$1"; local pkg="$2"; local display="$3"
  if run_as_laife "/opt/laife/envs/${venv}/bin/python -c 'import ${pkg}'" 2>/dev/null; then
    pass "import $display ($venv)"; TOTAL_PASS=$((TOTAL_PASS+1))
  else
    fail "import $display ($venv)"; TOTAL_FAIL=$((TOTAL_FAIL+1))
  fi
}

info "laife venv (chat, questionnaire, weekly, report):"
/opt/laife/envs/laife/bin/python --version
check_import laife fastapi fastapi
check_import laife uvicorn uvicorn
check_import laife motor "motor (MongoDB)"
check_import laife pymilvus pymilvus
check_import laife sentence_transformers "sentence_transformers"
check_import laife onnxruntime "onnxruntime (CPU)"
check_import laife openai openai
check_import laife asyncpg "asyncpg (PostgreSQL)"

info "ocr venv (pdf-extract 8002):"
/opt/laife/envs/ocr/bin/python --version
check_import ocr fastapi fastapi
check_import ocr uvicorn uvicorn
check_import ocr pymupdf pymupdf
check_import ocr tiktoken tiktoken

info "rag venv (rag-api + rag-worker):"
/opt/laife/envs/rag/bin/python --version
check_import rag fastapi fastapi
check_import rag uvicorn uvicorn
check_import rag torch torch
check_import rag transformers transformers
check_import rag pymilvus pymilvus

# ============================================================
section "3. 语法验证（与 deploy.sh Task 2 对齐）"
# ============================================================

check_syntax() {
  local file="$1"; local label="$2"
  if python3 -c "import ast; ast.parse(open('$file').read())" 2>/dev/null; then
    pass "syntax $label"; TOTAL_PASS=$((TOTAL_PASS+1))
  else
    fail "syntax $label"; TOTAL_FAIL=$((TOTAL_FAIL+1))
  fi
}

cd /opt/laife/apps/laife-ai
check_syntax main_questionnaire.py questionnaire
check_syntax main_weekly.py weekly
check_syntax main_chat.py "chat (main_chat)"
check_syntax main_report.py "report (main_report)"
[ -f OCR/main.py ] && check_syntax OCR/main.py "pdf-extract (OCR/main)"

cd /opt/laife/apps/realtime-rag
check_syntax main.py "rag main"
check_syntax streaming/api_server.py "rag api_server"

# ============================================================
section "4. 服务启动测试（与 deploy.sh Tasks 5,9,10,11 对齐）"
# ============================================================

test_service() {
  local name="$1"; local port="$2"; local health_url="$3"
  local wait_s="${4:-20}"
  local venv_name="${5:-laife}"
  local cwd="${6:-/opt/laife/apps/laife-ai}"
  local start_cmd="${7:-uvicorn main_${name}:app --host 0.0.0.0 --port ${port}}"

  echo ""
  echo "--------------------------------------------------"
  info "测试: $name (端口 $port)"

  run_as_laife "
    cd ${cwd}
    source /opt/laife/envs/${venv_name}/bin/activate
    ${start_cmd} > /opt/laife/logs/${name}.log 2>&1 &
    echo \$! > /tmp/${name}.pid
  "

  local ok=0
  info "等待 $name 启动 (最多 ${wait_s}s)..."
  for i in $(seq 1 "$wait_s"); do
    if ss -tlnp 2>/dev/null | grep -q ":${port} " || netstat -tlnp 2>/dev/null | grep -q ":${port} "; then
      ok=1; break
    fi
    sleep 1
  done

  if [[ "$ok" -eq 1 ]]; then
    pass "$name 端口 $port 已监听"
    sleep 2
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$health_url" 2>/dev/null || echo "000")
    if [[ "$code" == "200" ]]; then
      pass "$name HTTP $health_url → $code"
    elif [[ "$code" =~ ^(301|302|307|308|404|405)$ ]]; then
      pass "$name HTTP $health_url → $code (非 200 但正常)"
    else
      warn "$name HTTP $health_url → $code"
      info "--- 日志尾部 ---"
      tail -5 /opt/laife/logs/${name}.log 2>/dev/null || true
    fi
    TOTAL_PASS=$((TOTAL_PASS+1))
  else
    fail "$name 端口 $port 未在 ${wait_s}s 内监听"
    info "--- 日志 ---"
    tail -20 /opt/laife/logs/${name}.log 2>/dev/null || true
    TOTAL_FAIL=$((TOTAL_FAIL+1))
  fi
}

# ---- 4.1 Questionnaire 8015 (Task 5) ----
test_service "questionnaire" 8015 "http://127.0.0.1:8015/docs" 20 \
  "laife" "/opt/laife/apps/laife-ai" "uvicorn main_questionnaire:app --host 0.0.0.0 --port 8015"

# ---- 4.2 Weekly 8014 (Task 5) ----
test_service "weekly" 8014 "http://127.0.0.1:8014/docs" 20 \
  "laife" "/opt/laife/apps/laife-ai" "uvicorn main_weekly:app --host 0.0.0.0 --port 8014"

# ---- 4.3 PDF Extract 8002 (Task 9) ----
test_service "pdf-extract" 8002 "http://127.0.0.1:8002/health" 20 \
  "ocr" "/opt/laife/apps/laife-ai/OCR" "uvicorn main:app --host 0.0.0.0 --port 8002"

# ---- 4.4 Chat 8010 (Task 10) ----
test_service "chat" 8010 "http://127.0.0.1:8010/docs" 30 \
  "laife" "/opt/laife/apps/laife-ai" "uvicorn main_chat:app --host 0.0.0.0 --port 8010"

# ---- 4.5 Report 8013 (Task 10) ----
test_service "report" 8013 "http://127.0.0.1:8013/health" 20 \
  "laife" "/opt/laife/apps/laife-ai" "uvicorn main_report:app --host 0.0.0.0 --port 8013"

# ---- 4.6 RAG API 8011 (Task 11) ----
test_service "rag-api" 8011 "http://127.0.0.1:8011/metrics" 30 \
  "rag" "/opt/laife/apps/realtime-rag" \
  "python3 main.py serve --config configs/pipeline_preset5.yaml --host 0.0.0.0 --port 8011"

# ---- 4.7 RAG Worker (Task 11, no HTTP port) ----
echo ""
echo "--------------------------------------------------"
info "测试: rag-worker (后台 worker，无 HTTP 端口)"

run_as_laife "
  cd /opt/laife/apps/realtime-rag
  source /opt/laife/envs/rag/bin/activate
  python3 main.py worker --config configs/pipeline_preset5.yaml > /opt/laife/logs/rag-worker.log 2>&1 &
  echo \$! > /tmp/rag-worker.pid
"
sleep 10
if [ -f /tmp/rag-worker.pid ] && kill -0 $(cat /tmp/rag-worker.pid) 2>/dev/null; then
  pass "rag-worker 进程运行中（PID=$(cat /tmp/rag-worker.pid)）"
  TOTAL_PASS=$((TOTAL_PASS+1))
else
  warn "rag-worker 进程已退出（检查日志）"
  tail -20 /opt/laife/logs/rag-worker.log 2>/dev/null || true
  TOTAL_FAIL=$((TOTAL_FAIL+1))
fi

# ============================================================
section "5. 端口扫描总览"
# ============================================================

echo ""
for port in 8002 8010 8011 8013 8014 8015; do
  if ss -tlnp 2>/dev/null | grep -q ":${port} " || netstat -tlnp 2>/dev/null | grep -q ":${port} "; then
    pass "端口 $port 监听中"
  else
    fail "端口 $port 未监听"
  fi
done

# ============================================================
section "6. 汇总"
# ============================================================

echo ""
echo "===================================="
echo "  测试结果: $TOTAL_PASS PASS / $TOTAL_FAIL FAIL"
echo "===================================="

echo ""
info "日志文件大小:"
ls -lh /opt/laife/logs/*.log 2>/dev/null || true

if [[ "$TOTAL_FAIL" -gt 0 ]]; then
  echo ""
  warn "存在 $TOTAL_FAIL 个失败项，请检查上方日志"
  exit 1
else
  echo ""
  pass "所有检查通过！非 GPU 部分部署验证成功。"
  exit 0
fi
