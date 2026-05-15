# Laife 服务裸机部署手册 v2.0

> 逐行复制执行。每段末尾有验收命令，通过再继续。`<...>` 占位符需先替换。
> 全部代码修复已合入仓库，git clone 即可，无需手动改源码。

---

## 前置信息

| 变量 | 含义 | 值 |
|------|------|----|
| `<MONGO_HOST>` | MongoDB IP | |
| `<MONGO_PWD>` | MongoDB admin 密码 | |
| `<PG_HOST>` | PostgreSQL IP | |
| `<PG_PWD>` | PostgreSQL admin 密码 | |
| `<MILVUS_HOST>` | Milvus IP | |
| `<MILVUS_PORT>` | Milvus 端口 | 8050 |
| `<DASHSCOPE_API_KEY>` | 阿里云 Dashscope | |
| `<KB_API_KEY>` | 知识库中间层 | |
| `<QWEN_API_KEY>` | Dashscope (RAG) | |
| `<KIMI_API_KEY>` | Moonshot | |
| `<LAIFE_REPO>` | laife-ai git 地址 | |
| `<RAG_REPO>` | realtime-rag git 地址 | |

`PDF_API_KEY` 自生成：`openssl rand -hex 16`

---

## Task 1 — 服务器底座

```bash
# 1.1 系统依赖
sudo apt-get update && sudo apt-get install -y \
  build-essential git curl rsync \
  libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender1 \
  libgomp1 poppler-utils ffmpeg libsndfile1 logrotate jq

# 1.2 NVIDIA 驱动（若未装）
sudo apt-get install -y nvidia-driver-550 && sudo reboot
# 重启后:
nvidia-smi   # 必须列出 GPU

# 1.3 uv
curl -LsSf https://astral.sh/uv/install.sh | sh
sudo mv ~/.local/bin/uv /usr/local/bin/uv
uv --version

# 1.4 用户 & 目录
sudo groupadd --system laife
sudo useradd --system --gid laife --shell /usr/sbin/nologin --home /opt/laife laife
sudo mkdir -p /opt/laife/{apps,envs,models,config,data,logs,bin,docs}
sudo mkdir -p /opt/laife/apps/{laife-ai,realtime-rag}
sudo mkdir -p /opt/laife/envs/{ocr,paddle,laife,rag,vllm}
sudo mkdir -p /opt/laife/logs/{laife-ai,realtime-rag}
sudo mkdir -p /opt/laife/data/{uploads,sqlite,ocr-cache,rag}
sudo chown -R laife:laife /opt/laife
sudo chmod 750 /opt/laife/config

# 1.5 systemd slice
sudo tee /etc/systemd/system/laife-base.slice >/dev/null <<'EOF'
[Slice]
Description=Laife services slice
CPUAccounting=true
MemoryAccounting=true
IOAccounting=true
EOF
sudo systemctl daemon-reload && sudo systemctl start laife-base.slice

# 1.6 拉代码
cd /opt/laife/apps
sudo -u laife git clone <LAIFE_REPO> laife-ai
sudo -u laife git clone <RAG_REPO> realtime-rag
```

**验收：**
```bash
[[ -d /opt/laife/apps/laife-ai ]] && echo "PASS laife-ai"
[[ -d /opt/laife/apps/realtime-rag ]] && echo "PASS realtime-rag"
id laife && echo "PASS user"
uv --version && echo "PASS uv"
nvidia-smi -L && echo "PASS gpu"
systemctl is-active laife-base.slice && echo "PASS slice"
```

---

## Task 2 — 配置 & systemd

### 2.1 services.env

```bash
sudo tee /opt/laife/config/services.env >/dev/null <<'EOF'
# === 中间件 ===
MONGODB_URI=mongodb://admin:<MONGO_PWD>@<MONGO_HOST>:8060/chat_db?authSource=admin
MONGODB_ARCHIVE_URI=mongodb://admin:<MONGO_PWD>@<MONGO_HOST>:8060/health_archives?authSource=admin
PG_DSN=postgresql://admin:<PG_PWD>@<PG_HOST>:8070/laife_ai
MILVUS_HOST=<MILVUS_HOST>
MILVUS_PORT=<MILVUS_PORT>

# === 内部服务地址 ===
VLLM_BASE_URL=http://127.0.0.1:8005/v1
EMBEDDING_API_URL=http://127.0.0.1:8003/v1/embeddings
MINERU_API_HOST=127.0.0.1
MINERU_API_PORT=8000
PADDLE_OCR_URL=http://127.0.0.1:8001/ocr

# === 模型路径 ===
LOCAL_MODEL_NAME=/opt/laife/models/Qwen3.5-4B
ENTITY_MODEL_NAME=/opt/laife/models/Qwen3.5-4B
LAIFE_INTENT_ROUTER_MODEL=/opt/laife/models/Qwen3.5-4B
ASR_MODEL_PATH=/opt/laife/models/Qwen3-ASR-0.6B
MINERU_TOOLS_CONFIG_JSON=/opt/laife/config/mineru.json
QUES2LABEL_CHECKPOINT_DIR=/opt/laife/models/ques2label/hfl_enhance_all_textcnn_0.8
YUAN_EMBEDDING_PATH=/opt/laife/models/Yuan_embedding
PADDLE_DET_DIR=/opt/laife/models/paddle-ocr-model/det/ch/ch_PP-OCRv4_det_infer/
PADDLE_REC_DIR=/opt/laife/models/paddle-ocr-model/rec/ch/ch_PP-OCRv4_rec_infer/
PADDLE_CLS_DIR=/opt/laife/models/paddle-ocr-model/cls/ch_ppocr_mobile_v2.0_cls_infer/

# === RAG 数据路径 ===
RAG_REVIEW_DB=/opt/laife/data/sqlite/pending_reviews.db
JOB_STORE_DB_PATH=/opt/laife/data/sqlite/job_tasks.db
RAG_UPLOAD_DIR=/opt/laife/data/uploads

# === 其它 ===
KB_API_URL=http://172.20.8.12:8000/chat/stream
LAIFE_MCP_URL=http://127.0.0.1:8004/mcp
PYTHONUNBUFFERED=1
EOF

# 替换占位符
sudo sed -i "s|<MONGO_HOST>|<实际IP>|g; s|<MONGO_PWD>|<实际密码>|g" /opt/laife/config/services.env
sudo sed -i "s|<PG_HOST>|<实际IP>|g; s|<PG_PWD>|<实际密码>|g" /opt/laife/config/services.env
sudo sed -i "s|<MILVUS_HOST>|<实际IP>|g; s|<MILVUS_PORT>|<实际端口>|g" /opt/laife/config/services.env
sudo chown root:laife /opt/laife/config/services.env
sudo chmod 640 /opt/laife/config/services.env
```

### 2.2 secrets.env

```bash
sudo tee /opt/laife/config/secrets.env >/dev/null <<'EOF'
DASHSCOPE_API_KEY=<DASHSCOPE_API_KEY>
KB_API_KEY=<KB_API_KEY>
PDF_API_KEY=<PDF_API_KEY>
QWEN_API_KEY=<QWEN_API_KEY>
KIMI_API_KEY=<KIMI_API_KEY>
EOF
sudo chown root:laife /opt/laife/config/secrets.env
sudo chmod 640 /opt/laife/config/secrets.env
```

### 2.3 systemd 模板

```bash
sudo tee /etc/systemd/system/laife@.service >/dev/null <<'EOF'
[Unit]
Description=Laife CPU service (%i)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Slice=laife-base.slice
User=laife
Group=laife
WorkingDirectory=/opt/laife/apps/laife-ai
EnvironmentFile=/opt/laife/config/services.env
EnvironmentFile=/opt/laife/config/secrets.env
ExecStart=/opt/laife/bin/launch-%i.sh
Restart=always
RestartSec=5
StandardOutput=append:/opt/laife/logs/laife-ai/%i.log
StandardError=append:/opt/laife/logs/laife-ai/%i.err
LimitNOFILE=65535
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/opt/laife/data /opt/laife/logs /opt/laife/apps

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/laife-gpu@.service >/dev/null <<'EOF'
[Unit]
Description=Laife GPU service (%i)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Slice=laife-base.slice
User=laife
Group=laife
WorkingDirectory=/opt/laife/apps/laife-ai
EnvironmentFile=/opt/laife/config/services.env
EnvironmentFile=/opt/laife/config/secrets.env
Environment=CUDA_VISIBLE_DEVICES=0
Environment=PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512
ExecStart=/opt/laife/bin/launch-%i.sh
Restart=always
RestartSec=10
StandardOutput=append:/opt/laife/logs/laife-ai/%i.log
StandardError=append:/opt/laife/logs/laife-ai/%i.err
LimitNOFILE=65535
TimeoutStartSec=300
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/opt/laife/data /opt/laife/logs /opt/laife/apps /tmp

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/laife-rag@.service >/dev/null <<'EOF'
[Unit]
Description=Laife RAG service (%i)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Slice=laife-base.slice
User=laife
Group=laife
WorkingDirectory=/opt/laife/apps/realtime-rag
EnvironmentFile=/opt/laife/config/services.env
EnvironmentFile=/opt/laife/config/secrets.env
ExecStart=/opt/laife/bin/launch-rag-%i.sh
Restart=always
RestartSec=10
StandardOutput=append:/opt/laife/logs/realtime-rag/%i.log
StandardError=append:/opt/laife/logs/realtime-rag/%i.err
LimitNOFILE=65535
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/opt/laife/data /opt/laife/logs /opt/laife/apps

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemd-analyze verify /etc/systemd/system/laife@.service
sudo systemd-analyze verify /etc/systemd/system/laife-gpu@.service
sudo systemd-analyze verify /etc/systemd/system/laife-rag@.service
```

**验收：** 三个 `verify` 无报错；`ls -la /opt/laife/config/` 两个 env 文件 `-rw-r----- root laife`

---

## Task 3 — vLLM 8005（GPU）

```bash
# 1. rsync 模型（~10 min）
sudo -u laife rsync -aP zhenrong@47.98.227.81:/data/models/Qwen3.5-4B/ /opt/laife/models/Qwen3.5-4B/

# 2. venv + pip
sudo -u laife uv venv /opt/laife/envs/vllm --python 3.10
sudo -u laife /opt/laife/envs/vllm/bin/pip install vllm==0.19.0

# 3. launch
sudo tee /opt/laife/bin/launch-vllm.sh >/dev/null <<'SH'
#!/bin/bash
set -e
source /opt/laife/envs/vllm/bin/activate
exec vllm serve /opt/laife/models/Qwen3.5-4B \
  --port 8005 --tensor-parallel-size 1 --max-model-len 8192 \
  --reasoning-parser qwen3 --language-model-only --enable-prefix-caching \
  --gpu-memory-utilization 0.5 --max-num-seqs 32 --max-num-batched-tokens 8192 \
  --enable-auto-tool-choice --tool-call-parser qwen3_coder
SH
sudo chmod +x /opt/laife/bin/launch-vllm.sh
sudo chown laife:laife /opt/laife/bin/launch-vllm.sh

# 4. 启动（加载 ~3 min）
sudo systemctl enable --now laife-gpu@vllm.service
sleep 180

# 5. 验证
curl -fsS http://127.0.0.1:8005/v1/models | jq '.data[0].id'
# → /opt/laife/models/Qwen3.5-4B

curl -fsS http://127.0.0.1:8005/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"/opt/laife/models/Qwen3.5-4B","messages":[{"role":"user","content":"你好"}],"max_tokens":20}' | jq '.choices[0].message.content'

nvidia-smi --query-gpu=memory.used --format=csv,noheader
# ~24000 MiB
```

---

## Task 4 — Embedding 8003（GPU）

```bash
# 1. rsync 模型
sudo -u laife rsync -aP zhenrong@47.98.227.81:/data/models/embedding_model/ /opt/laife/models/embedding_model/

# 2. venv-laife（后续多个服务共用）
sudo -u laife uv venv /opt/laife/envs/laife --python 3.10
cd /opt/laife/apps/laife-ai
sudo -u laife /opt/laife/envs/laife/bin/pip install -r requirements.txt

# 3. launch
sudo tee /opt/laife/bin/launch-embedding.sh >/dev/null <<'SH'
#!/bin/bash
set -e
cd /opt/laife/apps/laife-ai
source /opt/laife/envs/laife/bin/activate
exec uvicorn RAG.embedding_api:app --host 0.0.0.0 --port 8003 --workers 1
SH
sudo chmod +x /opt/laife/bin/launch-embedding.sh
sudo chown laife:laife /opt/laife/bin/launch-embedding.sh

sudo systemctl enable --now laife-gpu@embedding.service
sleep 30

curl -fsS -X POST http://127.0.0.1:8003/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"input":"健康"}' | jq '.data[0].embedding | length'
# → 向量维度，如 768
```

---

## Task 5 — MinerU 8000（GPU）

```bash
# 1. scp 配置
sudo -u laife scp zhenrong@47.98.227.81:/data/conda/envs/ocr/mineru.json /opt/laife/config/mineru.json

# 2. venv-ocr
sudo -u laife uv venv /opt/laife/envs/ocr --python 3.10
cd /opt/laife/apps/laife-ai
sudo -u laife /opt/laife/envs/ocr/bin/pip install \
  mineru==3.1.2 fastapi uvicorn openai tiktoken pymupdf \
  pyahocorasick python-dateutil json_repair requests

# 3. 模型缓存（可选，省首次下载）
sudo -u laife rsync -aP zhenrong@47.98.227.81:~/.cache/modelscope/ /opt/laife/data/ocr-cache/modelscope/ || true
sudo -u laife rsync -aP zhenrong@47.98.227.81:~/.cache/huggingface/ /opt/laife/data/ocr-cache/huggingface/ || true

# 4. launch
sudo tee /opt/laife/bin/launch-mineru.sh >/dev/null <<'SH'
#!/bin/bash
set -e
export HF_HOME=/opt/laife/data/ocr-cache/huggingface
export MODELSCOPE_CACHE=/opt/laife/data/ocr-cache/modelscope
cd /opt/laife/apps/laife-ai
source /opt/laife/envs/ocr/bin/activate
exec uvicorn OCR.mineru_api:app --host 0.0.0.0 --port 8000
SH
sudo chmod +x /opt/laife/bin/launch-mineru.sh
sudo chown laife:laife /opt/laife/bin/launch-mineru.sh

sudo systemctl enable --now laife-gpu@mineru.service
sleep 60

curl -fsS http://127.0.0.1:8000/docs >/dev/null && echo "PASS 8000"
```

---

## Task 6 — PaddleOCR 8001（GPU）

```bash
# 1. rsync 模型
sudo -u laife rsync -aP zhenrong@47.98.227.81:/data/models/paddle-ocr-model/ /opt/laife/models/paddle-ocr-model/

# 2. venv-paddle
sudo -u laife uv venv /opt/laife/envs/paddle --python 3.10
sudo -u laife /opt/laife/envs/paddle/bin/pip install \
  "paddlepaddle-gpu==2.6.1.post120" -i https://www.paddlepaddle.org.cn/packages/stable/cu120/
sudo -u laife /opt/laife/envs/paddle/bin/pip install "paddleocr==2.7.0.3" flask pillow

# 3. launch
sudo tee /opt/laife/bin/launch-paddle-ocr.sh >/dev/null <<'SH'
#!/bin/bash
set -e
cd /opt/laife/apps/laife-ai
source /opt/laife/envs/paddle/bin/activate
exec python3 OCR/paddle-ocr.py
SH
sudo chmod +x /opt/laife/bin/launch-paddle-ocr.sh
sudo chown laife:laife /opt/laife/bin/launch-paddle-ocr.sh

sudo systemctl enable --now laife-gpu@paddle-ocr.service
sleep 20
curl -fsS http://127.0.0.1:8001/ && echo "PASS 8001"
```

---

## Task 7 — PDF Extract 8002（CPU）

```bash
# venv-ocr 已有
sudo tee /opt/laife/bin/launch-pdf-extract.sh >/dev/null <<'SH'
#!/bin/bash
set -e
cd /opt/laife/apps/laife-ai/OCR
source /opt/laife/envs/ocr/bin/activate
exec uvicorn main:app --host 0.0.0.0 --port 8002
SH
sudo chmod +x /opt/laife/bin/launch-pdf-extract.sh
sudo chown laife:laife /opt/laife/bin/launch-pdf-extract.sh

sudo systemctl enable --now laife@pdf-extract.service
sleep 10
curl -fsS http://127.0.0.1:8002/health && echo "PASS 8002"
```

---

## Task 8 — Questionnaire 8015 + Weekly 8014（CPU）

```bash
# venv-laife 已有，写 launch
for srv in "questionnaire:main_questionnaire:app:8015" "weekly:main_weekly:app:8014"; do
  name="${srv%%:*}"; rest="${srv#*:}"; mod="${rest%%:*}"
  rest="${rest#*:}"; appvar="${rest%%:*}"; port="${rest##*:}"
  sudo tee /opt/laife/bin/launch-${name}.sh >/dev/null <<SH
#!/bin/bash
set -e
cd /opt/laife/apps/laife-ai
source /opt/laife/envs/laife/bin/activate
exec uvicorn ${mod}:${appvar} --host 0.0.0.0 --port ${port}
SH
  sudo chmod +x /opt/laife/bin/launch-${name}.sh
  sudo chown laife:laife /opt/laife/bin/launch-${name}.sh
done

sudo systemctl enable --now laife@questionnaire.service
sleep 5 && curl -fsS http://127.0.0.1:8015/docs >/dev/null && echo "PASS 8015"

sudo systemctl enable --now laife@weekly.service
sleep 5 && curl -fsS "http://127.0.0.1:8014/weekly-report?user_id=test" | jq . && echo "PASS 8014"
```

---

## Task 9 — Chat 8010 + Report 8013 + ASR 8012

```bash
# 1. rsync 模型
sudo -u laife rsync -aP zhenrong@47.98.227.81:/data/models/Qwen3-ASR-0.6B/ /opt/laife/models/Qwen3-ASR-0.6B/
sudo -u laife mkdir -p /opt/laife/models/ques2label
sudo -u laife rsync -aP zhenrong@47.98.227.81:/data/laife-ai/ques2label/model/hfl_enhance_all_textcnn_0.8/ \
  /opt/laife/models/ques2label/hfl_enhance_all_textcnn_0.8/

# 2. launch 批量生成
for srv in "chat:main_chat:app:8010" "report:main_report:app:8013" "asr:main_asr:app:8012"; do
  name="${srv%%:*}"; rest="${srv#*:}"; mod="${rest%%:*}"
  rest="${rest#*:}"; appvar="${rest%%:*}"; port="${rest##*:}"
  sudo tee /opt/laife/bin/launch-${name}.sh >/dev/null <<SH
#!/bin/bash
set -e
cd /opt/laife/apps/laife-ai
source /opt/laife/envs/laife/bin/activate
exec uvicorn ${mod}:${appvar} --host 0.0.0.0 --port ${port}
SH
  sudo chmod +x /opt/laife/bin/launch-${name}.sh
  sudo chown laife:laife /opt/laife/bin/launch-${name}.sh
done

# 3. chat（最重，启动 45-60s）
sudo systemctl enable --now laife@chat.service
sleep 60 && curl -fsS http://127.0.0.1:8010/docs >/dev/null && echo "PASS 8010"

# 4. report
sudo systemctl enable --now laife@report.service
sleep 15 && curl -fsS http://127.0.0.1:8013/health && echo "PASS 8013"

# 5. ASR（GPU）
sudo systemctl enable --now laife-gpu@asr.service
sleep 90 && curl -fsS http://127.0.0.1:8012/health && echo "PASS 8012"
```

---

## Task 10 — RAG API + Worker 8011

```bash
# 1. rsync Yuan_embedding
sudo -u laife rsync -aP zhenrong@47.98.227.81:/home/wuteng/models/Yuan_embedding/ /opt/laife/models/Yuan_embedding/

# 2. venv-rag
sudo -u laife uv venv /opt/laife/envs/rag --python 3.10
cd /opt/laife/apps/realtime-rag
grep -v -E '^(rdkit|selfies|deepseek_ocr|vllm)' requirements.txt > /tmp/rag_filtered.txt
sudo -u laife /opt/laife/envs/rag/bin/pip install -r /tmp/rag_filtered.txt

# 3. launch
sudo tee /opt/laife/bin/launch-rag-api.sh >/dev/null <<'SH'
#!/bin/bash
set -e
cd /opt/laife/apps/realtime-rag
source /opt/laife/envs/rag/bin/activate
exec python3 main.py serve --config configs/pipeline_preset5.yaml --host 0.0.0.0 --port 8011
SH
sudo tee /opt/laife/bin/launch-rag-worker.sh >/dev/null <<'SH'
#!/bin/bash
set -e
cd /opt/laife/apps/realtime-rag
source /opt/laife/envs/rag/bin/activate
exec python3 main.py worker --config configs/pipeline_preset5.yaml
SH
sudo chmod +x /opt/laife/bin/launch-rag-{api,worker}.sh
sudo chown laife:laife /opt/laife/bin/launch-rag-{api,worker}.sh

sudo systemctl enable --now laife-rag@api.service
sleep 15 && curl -fsS http://127.0.0.1:8011/metrics | head && echo "PASS 8011 API"

sudo systemctl enable --now laife-rag@worker.service
sleep 5 && systemctl is-active laife-rag@worker.service && echo "PASS worker"
```

---

## Task 11 — 运维脚手架

```bash
# healthcheck
sudo tee /opt/laife/bin/healthcheck.sh >/dev/null <<'SH'
#!/bin/bash
RED="\033[0;31m"; GREEN="\033[0;32m"; NC="\033[0m"
declare -A EPS=(
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
  url="${EPS[$port]}"
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$url" 2>/dev/null || echo "---")
  if [[ "$code" == "200" ]]; then
    echo -e "${GREEN}PASS${NC} $port ($url -> $code)"
  else
    echo -e "${RED}FAIL${NC} $port ($url -> $code)"
    fail=1
  fi
done
exit $fail
SH
sudo chmod +x /opt/laife/bin/healthcheck.sh

# rollout
sudo tee /opt/laife/bin/rollout.sh >/dev/null <<'SH'
#!/bin/bash
set -e
svc="$1"; if [[ -z "$svc" ]]; then echo "usage: $0 <service>"; exit 2; fi
case "$svc" in
  rag-api|rag-worker) repo=/opt/laife/apps/realtime-rag; unit="laife-rag@${svc#rag-}.service" ;;
  mineru|paddle-ocr|embedding|asr|vllm) repo=/opt/laife/apps/laife-ai; unit="laife-gpu@${svc}.service" ;;
  *) repo=/opt/laife/apps/laife-ai; unit="laife@${svc}.service" ;;
esac
sudo -u laife git -C "$repo" pull && sudo systemctl restart "$unit"
sleep 15 && /opt/laife/bin/healthcheck.sh
SH
sudo chmod +x /opt/laife/bin/rollout.sh

# logrotate
sudo tee /etc/logrotate.d/laife >/dev/null <<'EOF'
/opt/laife/logs/*/*.log /opt/laife/logs/*/*.err {
  daily; rotate 14; compress; delaycompress
  missingok; notifempty; copytruncate; su laife laife
}
EOF
sudo logrotate -d /etc/logrotate.d/laife
```

---

## Task 12 — 最终验收

### Milvus 集合初始化（chat 启动必须）

```bash
source /opt/laife/envs/laife/bin/activate
python3 << 'PYEOF'
import os
from pymilvus import connections, Collection, FieldSchema, CollectionSchema, DataType, utility

host = os.getenv("MILVUS_HOST", "127.0.0.1")
port = os.getenv("MILVUS_PORT", "8050")
connections.connect(host=host, port=port)

for name in ["knowledge_health", "knowledge_product", "knowledge_book", "knowledge_personal_test"]:
    if name not in utility.list_collections():
        fields = [
            FieldSchema(name="id_1", dtype=DataType.VARCHAR, is_primary=True, max_length=256),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=768),
        ]
        schema = CollectionSchema(fields, description=name)
        c = Collection(name=name, schema=schema)
        c.create_index(field_name="embedding", index_params={
            "metric_type": "COSINE", "index_type": "IVF_FLAT", "params": {"nlist": 128}
        })
        c.load()
        print(f"  CREATED {name}")
    else:
        print(f"  EXISTS  {name}")
print("Done:", utility.list_collections())
PYEOF
```

### 全服务健康检查

```bash
/opt/laife/bin/healthcheck.sh
# 12 行全 PASS
```

### 业务链路

```bash
PDF_KEY=$(grep PDF_API_KEY /opt/laife/config/secrets.env | cut -d= -f2)

# PDF 提取
curl -fsS -X POST http://127.0.0.1:8002/process-pdf/ \
  -H "X-API-Key: $PDF_KEY" -F "file=@/tmp/sample.pdf" -F "file_type=其他" | jq '. | length'

# Chat
curl -fsS -N -X POST http://127.0.0.1:8010/chat/assistant \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test","session_id":"t1","message":"你好"}' | head -5

# 周报
curl -fsS "http://127.0.0.1:8014/weekly-report?user_id=test" | jq '.'

# 问卷
curl -fsS -X POST http://127.0.0.1:8015/questionnaire \
  -H "Content-Type: application/json" \
  -d '{"user_guid":"u1","questionnaire_guid":"q1","answers":{"a":"b"}}' | jq '.'

# RAG
curl -fsS http://127.0.0.1:8011/api/v1/tasks?limit=5 | jq '.'
```

### 重启演练

```bash
sudo reboot
# 重启后:
/opt/laife/bin/healthcheck.sh  # 12 行 PASS
```

---

## 故障排查

| 症状 | 命令 | 原因 |
|------|------|------|
| systemctl failed | `journalctl -u laife@chat -n 50 --no-pager` | ImportError / env / port |
| ModuleNotFoundError | `ls /opt/laife/envs/laife/lib/python3.10/site-packages/ \| grep <mod>` | pip 装漏 |
| 端口占用 | `sudo ss -ltnp \| grep :8010` | 旧进程 |
| GPU OOM | `nvidia-smi` | 显存超预算 |
| Mongo 超时 | `nc -vz <MONGO_HOST> 8060` | 防火墙 |
| MinerU 起不来 | `ls /opt/laife/config/mineru.json` | 忘记 scp |
| Milvus CollNotFound | `python3 -c "from pymilvus import utility; print(utility.list_collections())"` | 集合未建 |
| pip 冲突 | `pip check` | 手动 `>=` |

## 日常运维

```bash
/opt/laife/bin/rollout.sh chat          # 单服务发布
/opt/laife/bin/healthcheck.sh           # 全量检查
tail -f /opt/laife/logs/laife-ai/chat.log
journalctl -u laife@chat -f
```
