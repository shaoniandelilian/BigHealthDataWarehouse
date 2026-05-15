# Ubuntu 22.04 — 模拟 laife 裸机部署环境（非 GPU 部分）
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Shanghai

# ---- 系统依赖（与 deploy.sh Task 1 对齐）----
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends \
      build-essential git curl rsync \
      libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender1 \
      libgomp1 poppler-utils ffmpeg libsndfile1 \
      logrotate jq python3 python3-pip python3-venv \
      ca-certificates sudo iproute2 net-tools && \
    rm -rf /var/lib/apt/lists/*

# ---- 安装 uv ----
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    mv /root/.local/bin/uv /usr/local/bin/uv

# ---- 创建目录骨架（与 deploy.sh Task 1 对齐）----
RUN mkdir -p /opt/laife/{apps,envs,models,config,data,logs,bin,docs} && \
    mkdir -p /opt/laife/apps/{laife-ai,realtime-rag} && \
    mkdir -p /opt/laife/envs/{ocr,paddle,laife,rag,vllm} && \
    mkdir -p /opt/laife/logs/{laife-ai,realtime-rag} && \
    mkdir -p /opt/laife/data/{uploads,sqlite,ocr-cache,rag}

# ---- 创建工作用户 ----
RUN groupadd --system laife && \
    useradd --system --gid laife --shell /bin/bash --home /opt/laife laife && \
    chown -R laife:laife /opt/laife

# ---- 拷贝 deploy 配置文件 ----
COPY deploy-bundle/config/services.env /opt/laife/config/services.env
COPY deploy-bundle/config/secrets.env /opt/laife/config/secrets.env
COPY deploy-bundle/bin/ /opt/laife/bin/
RUN chmod +x /opt/laife/bin/*.sh && \
    chown -R laife:laife /opt/laife/bin && \
    chown root:laife /opt/laife/config/services.env /opt/laife/config/secrets.env && \
    chmod 640 /opt/laife/config/services.env /opt/laife/config/secrets.env

# ---- 拷贝源码 ----
COPY laife-ai/ /opt/laife/apps/laife-ai/
COPY realtime_rag_pipeline/ /opt/laife/apps/realtime-rag/
RUN chown -R laife:laife /opt/laife/apps

# ---- 安装 Python 虚拟环境 ----
# laife venv (CPU services: chat, questionnaire, weekly, report)
# 注意：必须安装 CPU 版 onnxruntime 替代 onnxruntime-gpu
RUN uv venv /opt/laife/envs/laife --python 3.10 --seed && \
    sed 's/onnxruntime-gpu/onnxruntime/g; s/vllm==0.19.0/# vllm==0.19.0 (GPU-only)/g; s/^qwen-asr==/# qwen-asr== (GPU-only)/g' /opt/laife/apps/laife-ai/requirements.txt > /tmp/laife_req_cpu.txt && \
    /opt/laife/envs/laife/bin/pip install --upgrade pip && \
    /opt/laife/envs/laife/bin/pip install -r /tmp/laife_req_cpu.txt 2>&1 | tail -5 && \
    echo "laife venv OK"

# ocr venv (PDF extract 8002)
RUN uv venv /opt/laife/envs/ocr --python 3.10 --seed && \
    /opt/laife/envs/ocr/bin/pip install --upgrade pip && \
    /opt/laife/envs/ocr/bin/pip install fastapi uvicorn openai tiktoken pymupdf pyahocorasick python-dateutil json_repair requests 2>&1 | tail -3 && \
    echo "ocr venv OK"

# rag venv (RAG API + Worker)
RUN uv venv /opt/laife/envs/rag --python 3.10 --seed && \
    grep -v -E '^(rdkit|selfies|deepseek_ocr|vllm)' /opt/laife/apps/realtime-rag/requirements.txt > /tmp/rag_req_filtered.txt && \
    /opt/laife/envs/rag/bin/pip install --upgrade pip && \
    /opt/laife/envs/rag/bin/pip install -r /tmp/rag_req_filtered.txt 2>&1 | tail -5 && \
    echo "rag venv OK"

# ---- 测试脚本 ----
COPY docker-test/test-deploy-non-gpu.sh /opt/laife/bin/test-deploy-non-gpu.sh
RUN chmod +x /opt/laife/bin/test-deploy-non-gpu.sh && \
    chown laife:laife /opt/laife/bin/test-deploy-non-gpu.sh

WORKDIR /opt/laife

# 默认命令：运行测试
CMD ["bash", "/opt/laife/bin/test-deploy-non-gpu.sh"]
