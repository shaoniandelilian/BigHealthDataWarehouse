#!/bin/bash
set -euo pipefail

# ============================================================
# Laife 裸机部署主脚本 v1.0
# 使用说明：
#   1. 将此脚本及相关配置文件 scp 到目标服务器
#   2. 以 root 身份执行: bash deploy.sh
#   3. 按提示填入前置信息
#   4. 脚本每个 Task 完成会暂停等待确认
# ============================================================

# ---- 颜色 ----
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; exit 1; }
info() { echo -e "${CYAN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
section() { echo ""; echo -e "${YELLOW}========================================${NC}"; echo -e "${YELLOW}  $1${NC}"; echo -e "${YELLOW}========================================${NC}"; }

# ---- 配置（执行前修改）----
# Git 仓库地址
LAIFE_AI_REPO="<git-repo-url-for-laife-ai>"
REALTIME_RAG_REPO="<git-repo-url-for-realtime-rag>"
LAIFE_AI_BRANCH="main"
REALTIME_RAG_BRANCH="main"

# 旧服务器 SSH（rsync 模型用）
OLD_SERVER="47.98.227.81"
OLD_SERVER_USER="zhenrong"

# ---- 检查 root ----
if [[ $EUID -ne 0 ]]; then
  fail "请以 root 身份运行此脚本"
fi

# ============================================================
# Phase A — 服务器底座（Task 1）
# ============================================================
section "Phase A — 服务器底座 (Task 1)"

# 1.1 OS 确认
info "检查 OS ..."
if ! grep -q "Ubuntu 22.04" /etc/os-release 2>/dev/null; then
  warn "当前 OS 不是 Ubuntu 22.04 LTS，请确认兼容性"
  read -p "按回车继续，或 Ctrl+C 中止 ..."
fi
pass "OS 检查完成"

# 1.2 apt 包
info "安装系统依赖包 ..."
apt-get update -qq
apt-get install -y build-essential git curl rsync \
  libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender1 \
  libgomp1 poppler-utils ffmpeg libsndfile1 \
  logrotate jq
pass "系统依赖包安装完成"

# 1.3 NVIDIA 驱动 + CUDA
info "安装 NVIDIA 驱动 ..."
if ! nvidia-smi &>/dev/null; then
  apt-get install -y nvidia-driver-550
  warn "驱动已安装，需要重启。请运行: sudo reboot"
  warn "重启后重新运行此脚本，从 --from-phase-b 继续"
  echo ""
  echo "  继续方式: bash deploy.sh --from-phase-b"
  exit 0
fi
DRV_VER=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1)
if [[ "$(echo $DRV_VER | cut -d. -f1)" -lt 550 ]]; then
  fail "驱动版本 $DRV_VER < 550，请手动升级"
fi
pass "NVIDIA 驱动 $DRV_VER"
nvidia-smi -L | head -3

# 1.4 安装 uv
info "安装 uv ..."
curl -LsSf https://astral.sh/uv/install.sh | sh
if [ -f "$HOME/.local/bin/uv" ]; then
  mv "$HOME/.local/bin/uv" /usr/local/bin/uv
elif [ -f /root/.local/bin/uv ]; then
  mv /root/.local/bin/uv /usr/local/bin/uv
fi
uv --version
pass "uv 安装完成"

# 1.5 创建系统用户
info "创建系统用户 laife ..."
groupadd --system laife 2>/dev/null || true
useradd --system --gid laife --shell /usr/sbin/nologin --home /opt/laife laife 2>/dev/null || true
id laife
pass "用户 laife 就绪"

# 1.6 目录骨架
info "创建目录骨架 ..."
mkdir -p /opt/laife/{apps,envs,models,config,data,logs,bin,docs}
mkdir -p /opt/laife/apps/{laife-ai,realtime-rag}
mkdir -p /opt/laife/envs/{ocr,paddle,laife,rag,vllm}
mkdir -p /opt/laife/logs/{laife-ai,realtime-rag}
mkdir -p /opt/laife/data/{uploads,sqlite,ocr-cache,rag}
chown -R laife:laife /opt/laife
chmod 750 /opt/laife/config
pass "目录骨架就绪"

# 1.7 systemd slice
info "创建 laife-base.slice ..."
cat > /etc/systemd/system/laife-base.slice <<'EOF'
[Slice]
Description=Laife services slice
CPUAccounting=true
MemoryAccounting=true
IOAccounting=true
EOF
systemctl daemon-reload
systemctl start laife-base.slice
pass "laife-base.slice 已启动"

# ---- Task 1 验收 ----
section "Task 1 验收"
[[ -d /opt/laife/apps ]] && pass "dir apps" || fail "dir apps"
[[ -d /opt/laife/envs/ocr ]] && pass "dir envs" || fail "dir envs"
id laife &>/dev/null && pass "user laife" || fail "user laife"
uv --version &>/dev/null && pass "uv" || fail "uv"
nvidia-smi -L &>/dev/null && pass "gpu" || fail "gpu"
systemctl is-active laife-base.slice &>/dev/null && pass "slice" || fail "slice"

echo ""
read -p "Task 1 验收完成，按回车继续 Phase B ..."

# ============================================================
# Phase B — 代码修复（Task 2）
# ============================================================
section "Phase B — 代码修复 (Task 2)"

# 2.1 克隆源码
info "克隆 laife-ai ..."
cd /opt/laife/apps
if [ ! -d laife-ai/.git ]; then
  sudo -u laife git clone "$LAIFE_AI_REPO" laife-ai
  cd laife-ai
  sudo -u laife git checkout "$LAIFE_AI_BRANCH"
  sudo -u laife git checkout -b deploy/bare-metal-v1
else
  info "laife-ai 已存在，跳过克隆"
fi

info "克隆 realtime-rag ..."
cd /opt/laife/apps
if [ ! -d realtime-rag/.git ]; then
  sudo -u laife git clone "$REALTIME_RAG_REPO" realtime-rag
  cd realtime-rag
  sudo -u laife git checkout "$REALTIME_RAG_BRANCH"
else
  info "realtime-rag 已存在，跳过克隆"
fi

# 2.2 应用 7 处代码修改（如果代码还没合并）
section "应用 7 处代码修改"

info "修改 1: OCR/utils.py — 删除 CUDA_VISIBLE_DEVICES 硬编码"
cd /opt/laife/apps/laife-ai
if grep -q 'os.environ\["CUDA_VISIBLE_DEVICES"\]' OCR/utils.py; then
  sed -i '/os\.environ\["CUDA_VISIBLE_DEVICES"\]/d' OCR/utils.py
  pass "修改 1 完成"
else
  pass "修改 1 已应用，跳过"
fi

info "修改 2: OCR/utils.py — MINERU_TOOLS_CONFIG_JSON 路径 env 化"
if grep -q '/data/conda/envs/ocr/mineru.json' OCR/utils.py; then
  sed -i 's|os.environ\["MINERU_TOOLS_CONFIG_JSON"\] = "/data/conda/envs/ocr/mineru.json"|os.environ.setdefault("MINERU_TOOLS_CONFIG_JSON", "/opt/laife/config/mineru.json")|' OCR/utils.py
  pass "修改 2 完成"
else
  pass "修改 2 已应用，跳过"
fi

info "修改 3: OCR/utils.py — PaddleOCR URL 从 env 读"
if grep -q "'http://127.0.0.1:8001/ocr'" OCR/utils.py; then
  sed -i "s|url = f'http://127.0.0.1:8001/ocr'|url = os.getenv(\"PADDLE_OCR_URL\", \"http://127.0.0.1:8001/ocr\")|" OCR/utils.py
  pass "修改 3 完成"
else
  pass "修改 3 已应用，跳过"
fi

info "修改 4: OCR/paddle-ocr.py — 模型路径从 env 读"
if grep -q '/data/models/paddle-ocr-model' OCR/paddle-ocr.py; then
  sed -i 's|det_model_dir="/data/models/paddle-ocr-model/det/ch/ch_PP-OCRv4_det_infer/"|det_model_dir=os.getenv("PADDLE_DET_DIR", "/opt/laife/models/paddle-ocr-model/det/ch/ch_PP-OCRv4_det_infer/")|' OCR/paddle-ocr.py
  sed -i 's|rec_model_dir="/data/models/paddle-ocr-model/rec/ch/ch_PP-OCRv4_rec_infer/"|rec_model_dir=os.getenv("PADDLE_REC_DIR", "/opt/laife/models/paddle-ocr-model/rec/ch/ch_PP-OCRv4_rec_infer/")|' OCR/paddle-ocr.py
  sed -i 's|cls_model_dir="/data/models/paddle-ocr-model/cls/ch_ppocr_mobile_v2.0_cls_infer/"|cls_model_dir=os.getenv("PADDLE_CLS_DIR", "/opt/laife/models/paddle-ocr-model/cls/ch_ppocr_mobile_v2.0_cls_infer/")|' OCR/paddle-ocr.py
  pass "修改 4 完成"
else
  pass "修改 4 已应用，跳过"
fi

info "修改 5: OCR/mineru_api.py — 默认 mineru.json 路径"
if grep -q '/data/conda/envs/ocr/mineru.json' OCR/mineru_api.py; then
  sed -i 's|_default_magic_cfg = "/data/conda/envs/ocr/mineru.json"|_default_magic_cfg = "/opt/laife/config/mineru.json"|' OCR/mineru_api.py
  pass "修改 5 完成"
else
  pass "修改 5 已应用，跳过"
fi

info "修改 6: realtime-rag configs/pipeline_preset5.yaml — API key 占位符"
cd /opt/laife/apps/realtime-rag
if grep -q 'sk-0228e8728fd34b43b93a831d664ddceb' configs/pipeline_preset5.yaml; then
  sed -i 's|qwen_api_key: "sk-0228e8728fd34b43b93a831d664ddceb"|qwen_api_key: "${QWEN_API_KEY}"|' configs/pipeline_preset5.yaml
  sed -i 's|kimi_api_key: "sk-F0FLPR7UbuCVngJrKjKZM33QpS7upySVtRSlOQiqkoNUwfMX"|kimi_api_key: "${KIMI_API_KEY}"|' configs/pipeline_preset5.yaml
  pass "修改 6a YAML 完成"
else
  pass "修改 6a YAML 已应用，跳过"
fi

info "修改 6b: multi_llm_filter.py — 添加 ${VAR} 展开"
cd /opt/laife/apps/realtime-rag
if ! grep -q '_expand' processors/transformation/multi_llm_filter.py; then
  # 在 super().__init__() 之后插入 env 展开逻辑
  sed -i '/super().__init__()/a\
\n        # 展开 ${VAR} 占位符（从 YAML 加载时不会自动替换）\
        _re_env = re.compile(r"\\${(\\w+)}")\
        def _expand(val):\
            if isinstance(val, str):\
                return _re_env.sub(lambda m: os.environ.get(m.group(1), ""), val)\
            return val\
        deepseek_api_key = _expand(deepseek_api_key)\
        qwen_api_key = _expand(qwen_api_key)\
        kimi_api_key = _expand(kimi_api_key)' processors/transformation/multi_llm_filter.py
  pass "修改 6b 完成"
else
  pass "修改 6b 已应用，跳过"
fi

info "修改 7: realtime-rag api_server.py — 路径 env 化"
if grep -q 'db_path="logs/pending_reviews.db"' streaming/api_server.py; then
  sed -i 's|ReviewStore(db_path="logs/pending_reviews.db")|ReviewStore(db_path=os.getenv("RAG_REVIEW_DB", "/opt/laife/data/sqlite/pending_reviews.db"))|' streaming/api_server.py
  pass "修改 7a review_store 完成"
else
  pass "修改 7a 已应用，跳过"
fi
if grep -q 'db_path=os.getenv("JOB_STORE_DB_PATH", "logs/job_tasks.db")' streaming/api_server.py; then
  sed -i 's|db_path=os.getenv("JOB_STORE_DB_PATH", "logs/job_tasks.db")|db_path=os.getenv("JOB_STORE_DB_PATH", "/opt/laife/data/sqlite/job_tasks.db")|' streaming/api_server.py
  pass "修改 7b job_store 完成"
else
  pass "修改 7b 已应用，跳过"
fi
if grep -q 'UPLOAD_DIR = Path("data/uploads")' streaming/api_server.py; then
  sed -i 's|UPLOAD_DIR = Path("data/uploads")|UPLOAD_DIR = Path(os.getenv("RAG_UPLOAD_DIR", "/opt/laife/data/uploads"))|' streaming/api_server.py
  pass "修改 7c UPLOAD_DIR 完成"
else
  pass "修改 7c 已应用，跳过"
fi

# 2.3 语法验证
section "语法验证"
cd /opt/laife/apps/laife-ai
python3 -c "import ast; ast.parse(open('OCR/utils.py').read())" && pass "syntax utils" || fail "syntax utils"
python3 -c "import ast; ast.parse(open('OCR/mineru_api.py').read())" && pass "syntax mineru_api" || fail "syntax mineru_api"
python3 -c "import ast; ast.parse(open('OCR/paddle-ocr.py').read())" && pass "syntax paddle-ocr" || fail "syntax paddle-ocr"
cd /opt/laife/apps/realtime-rag
python3 -c "import ast; ast.parse(open('processors/transformation/multi_llm_filter.py').read())" && pass "syntax multi_llm_filter" || fail "syntax multi_llm_filter"
python3 -c "import ast; ast.parse(open('streaming/api_server.py').read())" && pass "syntax api_server" || fail "syntax api_server"
# yaml 验证需装 pyyaml，不阻塞
python3 -c "import yaml; yaml.safe_load(open('configs/pipeline_preset5.yaml'))" 2>/dev/null && pass "yaml" || warn "yaml 验证需要 pyyaml 库，部署后手动验证"

echo ""
read -p "Task 2 完成。提交修改到 git？(y/n): " yn_git
if [[ "$yn_git" == "y" ]]; then
  cd /opt/laife/apps/laife-ai
  git add -A
  git commit -m "deploy: externalize hardcoded paths and API keys for bare-metal v1"
  git push origin deploy/bare-metal-v1
  warn "等待 review + merge 回 main，然后切回: git checkout main && git pull"
fi
read -p "按回车继续 Phase C ..."

# ============================================================
# Phase C — 配置与 systemd 模板（Task 3）
# ============================================================
section "Phase C — 配置与 systemd 模板 (Task 3)"

# 询问中间件地址
echo ""
info "请提供中间件连接信息："
read -p "  MongoDB 主机: " MONGO_HOST
read -p "  MongoDB 密码: " MONGO_PWD
read -p "  PostgreSQL 主机: " PG_HOST
read -p "  PostgreSQL 密码: " PG_PWD
read -p "  Milvus 主机: " MILVUS_HOST

# 创建 services.env
info "生成 /opt/laife/config/services.env ..."
cp "$(dirname "$0")/config/services.env" /opt/laife/config/services.env
sed -i "s|<MONGO_HOST>|$MONGO_HOST|g" /opt/laife/config/services.env
sed -i "s|<MONGO_PWD>|$MONGO_PWD|g" /opt/laife/config/services.env
sed -i "s|<PG_HOST>|$PG_HOST|g" /opt/laife/config/services.env
sed -i "s|<PG_PWD>|$PG_PWD|g" /opt/laife/config/services.env
sed -i "s|<MILVUS_HOST>|$MILVUS_HOST|g" /opt/laife/config/services.env
chown root:laife /opt/laife/config/services.env
chmod 640 /opt/laife/config/services.env
pass "services.env 已生成"

# 创建 secrets.env
info "生成 /opt/laife/config/secrets.env ..."
echo ""
info "请提供外部 API Key（留空则保持占位符，后续手动编辑）："
read -p "  DASHSCOPE_API_KEY: " v_dashscope
read -p "  KB_API_KEY: " v_kb
read -p "  PDF_API_KEY（留空自动生成）: " v_pdf
read -p "  QWEN_API_KEY: " v_qwen
read -p "  KIMI_API_KEY: " v_kimi

if [ -z "$v_pdf" ]; then v_pdf=$(openssl rand -hex 16); info "  自动生成 PDF_API_KEY: $v_pdf"; fi

cat > /opt/laife/config/secrets.env <<EOF
DASHSCOPE_API_KEY=${v_dashscope:-<DASHSCOPE_API_KEY>}
KB_API_KEY=${v_kb:-<KB_API_KEY>}
PDF_API_KEY=${v_pdf:-<PDF_API_KEY>}
QWEN_API_KEY=${v_qwen:-<QWEN_API_KEY>}
KIMI_API_KEY=${v_kimi:-<KIMI_API_KEY>}
EOF
chown root:laife /opt/laife/config/secrets.env
chmod 640 /opt/laife/config/secrets.env
pass "secrets.env 已生成"

# 安装 systemd 模板
info "安装 systemd 模板 ..."
cp "$(dirname "$0")/systemd/laife@.service" /etc/systemd/system/
cp "$(dirname "$0")/systemd/laife-gpu@.service" /etc/systemd/system/
cp "$(dirname "$0")/systemd/laife-rag@.service" /etc/systemd/system/
systemctl daemon-reload
systemd-analyze verify /etc/systemd/system/laife@.service
systemd-analyze verify /etc/systemd/system/laife-gpu@.service
systemd-analyze verify /etc/systemd/system/laife-rag@.service
pass "systemd 模板验证通过"

echo ""
read -p "Task 3 完成。按回车继续 Phase D ..."

# ============================================================
# Phase D — 服务上线（Tasks 4-11）
# ============================================================
section "Phase D — 服务上线"

# ---- 辅助函数 ----
deploy_launch_script() {
  local name="$1"
  local src="$2"
  cp "$src" "/opt/laife/bin/launch-${name}.sh"
  chmod +x "/opt/laife/bin/launch-${name}.sh"
  chown laife:laife "/opt/laife/bin/launch-${name}.sh"
  pass "launch-${name}.sh 就绪"
}

enable_gpu_service() {
  local name="$1"
  local sleep_sec="${2:-10}"
  systemctl enable --now "laife-gpu@${name}.service"
  info "等待 ${sleep_sec}s ..."
  sleep "$sleep_sec"
}

enable_cpu_service() {
  local name="$1"
  local sleep_sec="${2:-10}"
  systemctl enable --now "laife@${name}.service"
  info "等待 ${sleep_sec}s ..."
  sleep "$sleep_sec"
}

enable_rag_service() {
  local name="$1"
  local sleep_sec="${2:-10}"
  systemctl enable --now "laife-rag@${name}.service"
  info "等待 ${sleep_sec}s ..."
  sleep "$sleep_sec"
}

rsync_model() {
  local src="$1"
  local dst="$2"
  info "rsync $src -> $dst"
  sudo -u laife rsync -aP --info=progress2 "${OLD_SERVER_USER}@${OLD_SERVER}:${src}" "$dst"
}

# ============================================================
# Task 4 — vLLM 8005
# ============================================================
section "Task 4 — vLLM 8005"

info "rsync Qwen3.5-4B 模型（来自旧服务器 $OLD_SERVER）..."
read -p "是否跳过模型 rsync？(y/N): " skip_rsync_vllm
if [[ "$skip_rsync_vllm" != "y" ]]; then
  rsync_model "/data/models/Qwen3.5-4B/" "/opt/laife/models/Qwen3.5-4B/"
fi

info "创建 vllm venv ..."
sudo -u laife uv venv /opt/laife/envs/vllm --python 3.10
sudo -u laife /opt/laife/envs/vllm/bin/pip install vllm==0.19.0

deploy_launch_script "vllm" "$(dirname "$0")/bin/launch-vllm.sh"

info "启动 vllm（加载模型约 3 分钟）..."
enable_gpu_service "vllm" 180

info "验证 vLLM ..."
curl -fsS http://127.0.0.1:8005/v1/models | jq '.data[0].id' && pass "vLLM 模型加载" || warn "vLLM 模型加载检查失败"
curl -fsS http://127.0.0.1:8005/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"/opt/laife/models/Qwen3.5-4B","messages":[{"role":"user","content":"你好"}],"max_tokens":20}' \
  | jq '.choices[0].message.content' && pass "vLLM 推理" || warn "vLLM 推理检查失败"

echo ""
read -p "Task 4 完成。按回车继续 Task 5 ..."

# ============================================================
# Task 5 — Questionnaire 8015 + Weekly 8014
# ============================================================
section "Task 5 — Questionnaire 8015 + Weekly 8014"

info "创建 laife venv（CPU 服务共用）..."
sudo -u laife uv venv /opt/laife/envs/laife --python 3.10
cd /opt/laife/apps/laife-ai
sudo -u laife /opt/laife/envs/laife/bin/pip install -r requirements.txt

deploy_launch_script "questionnaire" "$(dirname "$0")/bin/launch-questionnaire.sh"
deploy_launch_script "weekly" "$(dirname "$0")/bin/launch-weekly.sh"

info "启动 questionnaire 8015..."
enable_cpu_service "questionnaire" 5
curl -fsS http://127.0.0.1:8015/docs > /dev/null && pass "Questionnaire 8015 在线" || warn "Questionnaire 8015 不可用"

info "启动 weekly 8014..."
enable_cpu_service "weekly" 5
curl -fsS "http://127.0.0.1:8014/weekly-report?user_id=test" -o /tmp/w.json 2>/dev/null || true
cat /tmp/w.json 2>/dev/null && pass "Weekly 8014 响应" || warn "Weekly 8014 响应空或 500"

read -p "Task 5 完成。按回车继续 Task 6 ..."

# ============================================================
# Task 6 — Embedding 8003
# ============================================================
section "Task 6 — Embedding 8003"

info "rsync embedding 模型..."
read -p "是否跳过模型 rsync？(y/N): " skip_rsync_emb
if [[ "$skip_rsync_emb" != "y" ]]; then
  rsync_model "/data/models/embedding_model/" "/opt/laife/models/embedding_model/"
fi

deploy_launch_script "embedding" "$(dirname "$0")/bin/launch-embedding.sh"

info "启动 embedding 8003（GPU）..."
enable_gpu_service "embedding" 30

curl -fsS -X POST http://127.0.0.1:8003/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"input":"健康"}' | jq '.data[0].embedding | length' && pass "Embedding 8003 向量生成" || warn "Embedding 8003 检查失败"

read -p "Task 6 完成。按回车继续 Task 7 ..."

# ============================================================
# Task 7 — MinerU 8000
# ============================================================
section "Task 7 — MinerU 8000"

info "scp mineru.json 配置..."
read -p "是否跳过 mineru.json 拉取？(y/N): " skip_mineru_cfg
if [[ "$skip_mineru_cfg" != "y" ]]; then
  sudo -u laife scp "${OLD_SERVER_USER}@${OLD_SERVER}:/data/conda/envs/ocr/mineru.json" /opt/laife/config/mineru.json
fi

info "创建 ocr venv（MinerU + PDF 提取）..."
sudo -u laife uv venv /opt/laife/envs/ocr --python 3.10
cd /opt/laife/apps/laife-ai
sudo -u laife /opt/laife/envs/ocr/bin/pip install mineru==3.1.2 fastapi uvicorn openai tiktoken pymupdf pyahocorasick python-dateutil json_repair requests

info "rsync MinerU 模型缓存（可选）..."
read -p "是否 rsync MinerU 缓存？(y/N): " skip_mineru_cache
if [[ "$skip_mineru_cache" == "y" ]]; then
  sudo -u laife rsync -aP "${OLD_SERVER_USER}@${OLD_SERVER}:~/.cache/modelscope/" /opt/laife/data/ocr-cache/modelscope/ || true
  sudo -u laife rsync -aP "${OLD_SERVER_USER}@${OLD_SERVER}:~/.cache/huggingface/" /opt/laife/data/ocr-cache/huggingface/ || true
fi

deploy_launch_script "mineru" "$(dirname "$0")/bin/launch-mineru.sh"

info "启动 mineru 8000（GPU）..."
enable_gpu_service "mineru" 60

# 验证 MinerU
if [ -f /opt/laife/apps/laife-ai/OCR/*.pdf ]; then
  cp /opt/laife/apps/laife-ai/OCR/*.pdf /tmp/sample.pdf 2>/dev/null || true
fi
if [ -f /tmp/sample.pdf ]; then
  mkdir -p /tmp/mineru-out
  curl -fsS -X POST http://127.0.0.1:8000/api/v1/parse \
    -H "Content-Type: application/json" \
    -d '{"pdf_path":"/tmp/sample.pdf","output_dir":"/tmp/mineru-out"}' && pass "MinerU 解析" || warn "MinerU 解析失败"
else
  warn "没有 sample.pdf，手动上传到 /tmp/ 后测试"
fi

read -p "Task 7 完成。按回车继续 Task 8 ..."

# ============================================================
# Task 8 — PaddleOCR 8001
# ============================================================
section "Task 8 — PaddleOCR 8001"

info "rsync PaddleOCR 模型..."
read -p "是否跳过模型 rsync？(y/N): " skip_rsync_paddle
if [[ "$skip_rsync_paddle" != "y" ]]; then
  rsync_model "/data/models/paddle-ocr-model/" "/opt/laife/models/paddle-ocr-model/"
fi

info "创建 paddle venv ..."
sudo -u laife uv venv /opt/laife/envs/paddle --python 3.10
sudo -u laife /opt/laife/envs/paddle/bin/pip install "paddlepaddle-gpu==2.6.1.post120" -i https://www.paddlepaddle.org.cn/packages/stable/cu120/
sudo -u laife /opt/laife/envs/paddle/bin/pip install "paddleocr==2.7.0.3" flask pillow

deploy_launch_script "paddle-ocr" "$(dirname "$0")/bin/launch-paddle-ocr.sh"

info "启动 paddle-ocr 8001（GPU）..."
enable_gpu_service "paddle-ocr" 20
curl -fsS http://127.0.0.1:8001/ && pass "PaddleOCR 8001 在线" || warn "PaddleOCR 8001 不可用"

if [ -f /tmp/test.jpg ]; then
  curl -fsS -X POST http://127.0.0.1:8001/ocr -F "image=@/tmp/test.jpg" | jq '.' && pass "PaddleOCR 识别" || warn "PaddleOCR 识别失败"
else
  warn "没有 /tmp/test.jpg，上传后手动测试: curl -X POST http://127.0.0.1:8001/ocr -F 'image=@/tmp/test.jpg'"
fi

read -p "Task 8 完成。按回车继续 Task 9 ..."

# ============================================================
# Task 9 — PDF Extract 8002
# ============================================================
section "Task 9 — PDF Extract 8002"

deploy_launch_script "pdf-extract" "$(dirname "$0")/bin/launch-pdf-extract.sh"

info "启动 pdf-extract 8002（CPU）..."
enable_cpu_service "pdf-extract" 10
curl -fsS http://127.0.0.1:8002/health && pass "PDF Extract 8002 健康" || warn "PDF Extract 8002 不可用"

# 端到端测试
if [ -f /tmp/sample.pdf ]; then
  PDF_KEY=$(grep PDF_API_KEY /opt/laife/config/secrets.env | cut -d= -f2)
  curl -fsS -X POST http://127.0.0.1:8002/process-pdf/ \
    -H "X-API-Key: $PDF_KEY" \
    -F "file=@/tmp/sample.pdf" -F "file_type=其他" | jq '. | length' && pass "PDF Extract 端到端" || warn "PDF Extract 端到端失败"
fi

read -p "Task 9 完成。按回车继续 Task 10 ..."

# ============================================================
# Task 10 — Health QA 8010 + Report 8013 + ASR 8012
# ============================================================
section "Task 10 — Health QA 8010 + Report 8013 + ASR 8012"

# rsync ASR 模型
info "rsync ASR 模型 + ques2label 模型..."
read -p "是否跳过模型 rsync？(y/N): " skip_rsync_asr
if [[ "$skip_rsync_asr" != "y" ]]; then
  rsync_model "/data/models/Qwen3-ASR-0.6B/" "/opt/laife/models/Qwen3-ASR-0.6B/"
  sudo -u laife mkdir -p /opt/laife/models/ques2label
  rsync_model "/data/laife-ai/ques2label/model/hfl_enhance_all_textcnn_0.8/" "/opt/laife/models/ques2label/hfl_enhance_all_textcnn_0.8/"
fi

# 部署 3 个 launch 脚本
deploy_launch_script "chat" "$(dirname "$0")/bin/launch-chat.sh"
deploy_launch_script "report" "$(dirname "$0")/bin/launch-report.sh"
deploy_launch_script "asr" "$(dirname "$0")/bin/launch-asr.sh"

# 顺序启用
info "启动 chat 8010（最重，加载慢）..."
enable_cpu_service "chat" 30
curl -fsS http://127.0.0.1:8010/docs > /dev/null && pass "Health QA 8010 在线" || warn "Health QA 8010 不可用"

info "启动 report 8013..."
enable_cpu_service "report" 15
curl -fsS http://127.0.0.1:8013/health && pass "Report 8013 在线" || warn "Report 8013 不可用"

info "启动 ASR 8012（GPU，模型加载约 1 分钟）..."
enable_gpu_service "asr" 90
curl -fsS http://127.0.0.1:8012/health && pass "ASR 8012 在线" || warn "ASR 8012 不可用"

read -p "Task 10 完成。按回车继续 Task 11 ..."

# ============================================================
# Task 11 — realtime_rag 8011 API + Worker
# ============================================================
section "Task 11 — realtime_rag 8011 API + Worker"

info "rsync Yuan_embedding 模型..."
read -p "是否跳过模型 rsync？(y/N): " skip_rsync_yuan
if [[ "$skip_rsync_yuan" != "y" ]]; then
  rsync_model "/home/wuteng/models/Yuan_embedding/" "/opt/laife/models/Yuan_embedding/"
fi

info "创建 rag venv ..."
sudo -u laife uv venv /opt/laife/envs/rag --python 3.10
cd /opt/laife/apps/realtime-rag
# 安装前先移除可能失败的可选依赖
if [ -f requirements.txt ]; then
  # 过滤掉可选的、不必要的大包
  grep -v -E '^(rdkit|selfies|deepseek_ocr|vllm)' requirements.txt > /tmp/rag_req_filtered.txt
  sudo -u laife /opt/laife/envs/rag/bin/pip install -r /tmp/rag_req_filtered.txt
fi

deploy_launch_script "rag-api" "$(dirname "$0")/bin/launch-rag-api.sh"
deploy_launch_script "rag-worker" "$(dirname "$0")/bin/launch-rag-worker.sh"

info "启动 rag-api 8011..."
enable_rag_service "api" 15
curl -fsS http://127.0.0.1:8011/metrics | head && pass "RAG API 8011 在线" || warn "RAG API 8011 不可用"

info "启动 rag-worker..."
enable_rag_service "worker" 5
systemctl status laife-rag@worker.service | head -5

read -p "Task 11 完成。按回车继续 Phase E ..."

# ============================================================
# Phase E — 运维脚手架（Task 12）
# ============================================================
section "Phase E — 运维脚手架 (Task 12)"

info "安装 healthcheck.sh ..."
cp "$(dirname "$0")/bin/healthcheck.sh" /opt/laife/bin/healthcheck.sh
chmod +x /opt/laife/bin/healthcheck.sh
chown laife:laife /opt/laife/bin/healthcheck.sh

info "安装 rollout.sh ..."
cp "$(dirname "$0")/bin/rollout.sh" /opt/laife/bin/rollout.sh
chmod +x /opt/laife/bin/rollout.sh
chown laife:laife /opt/laife/bin/rollout.sh

info "安装 logrotate 配置 ..."
cp "$(dirname "$0")/config/logrotate-laife" /etc/logrotate.d/laife
logrotate -d /etc/logrotate.d/laife 2>&1 | grep -q error && warn "logrotate 配置有误" || pass "logrotate 配置正确"

info "安装运维文档 ..."
mkdir -p /opt/laife/docs
cp "$(dirname "$0")/docs/GPU_BUDGET.md" /opt/laife/docs/GPU_BUDGET.md
cp "$(dirname "$0")/docs/RUNBOOK.md" /opt/laife/docs/RUNBOOK.md
chown -R laife:laife /opt/laife/docs

# ---- Task 12 验收 ----
section "Task 12 验收"
/opt/laife/bin/healthcheck.sh && pass "全服务健康" || warn "部分服务不健康"
[[ -x /opt/laife/bin/rollout.sh ]] && pass "rollout.sh" || fail "rollout.sh"
[[ -f /etc/logrotate.d/laife ]] && pass "logrotate" || fail "logrotate"
[[ -f /opt/laife/docs/GPU_BUDGET.md ]] && pass "GPU_BUDGET.md" || fail "GPU_BUDGET.md"
[[ -f /opt/laife/docs/RUNBOOK.md ]] && pass "RUNBOOK.md" || fail "RUNBOOK.md"

echo ""
read -p "Phase E 完成。按回车继续 Phase F（端到端验收）..."

# ============================================================
# Phase F — 端到端验收
# ============================================================
section "Phase F — 端到端验收"

echo "8.1 健康检查"
read -p "运行全量健康检查？(Y/n): " yn_hc
if [[ "$yn_hc" != "n" ]]; then
  /opt/laife/bin/healthcheck.sh
fi

echo ""
echo "8.2 业务链路回归测试（请手动准备样本）"
echo "  1. PDF 结构化提取: curl -X POST http://127.0.0.1:8002/process-pdf/"
echo "  2. 问答: curl -X POST http://127.0.0.1:8010/chat/assistant"
echo "  3. 周报: curl http://127.0.0.1:8014/weekly-report?user_id=test"
echo "  4. ASR: curl -X POST http://127.0.0.1:8012/asr/transcribe"
echo "  5. 问卷: curl -X POST http://127.0.0.1:8015/questionnaire"
echo "  6. RAG: curl http://127.0.0.1:8011/api/v1/tasks?limit=5"

echo ""
read -p "是否执行简单的全端口扫描？(Y/n): " yn_scan
if [[ "$yn_scan" != "n" ]]; then
  echo "端口扫描结果："
  for port in 8005 8000 8001 8003 8012 8002 8010 8013 8014 8015 8011; do
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 http://127.0.0.1:$port/ 2>/dev/null || echo "---")
    echo "  $port -> $code"
  done
fi

echo ""
section "部署完成！"
echo ""
echo "后续步骤："
echo "  1. 确认 Phase F 验收清单全部通过"
echo "  2. 执行业务链路回归测试"
echo "  3. 将业务流量切到新服务器"
echo "  4. 观察一周稳定后下线旧服务器 $OLD_SERVER"
echo ""
echo "日志路径: /opt/laife/logs/"
echo "健康检查: /opt/laife/bin/healthcheck.sh"
echo "滚动重启: /opt/laife/bin/rollout.sh <service>"
