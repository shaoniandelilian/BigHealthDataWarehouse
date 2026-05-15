# 47.98.227.81 服务端口总览

> 更新时间：2026-05-12

## 8000 — MinerU GPU 加速解析接口

- **框架**: FastAPI + uvicorn
- **进程**: `uvicorn OCR.mineru_api:app --host 0.0.0.0 --port 8000`
- **PID**: 2005916
- **环境**: `/data/conda/envs/ocr/`
- **接口**: `/api/v1/parse`（POST，同步阻塞 PDF 解析）
- **描述**: MinerU GPU 加速的 PDF 解析服务

---

## 8001 — PaddleOCR 服务

- **框架**: Python (非 FastAPI)
- **进程**: `python3 OCR/paddle-ocr.py`
- **PID**: 1779453, 2006519（两个实例）
- **环境**: `/data/conda/envs/paddle-ocr/`
- **接口**: 根路径返回 `OCR Service is running (PaddleOCR)`
- **描述**: 基于 PaddleOCR 的文字识别服务

---

## 8002 — PDF 结构化数据提取 API

- **框架**: FastAPI + uvicorn
- **进程**: `uvicorn main:app --host 0.0.0.0 --port 8002`
- **PID**: 40821
- **环境**: `/data/conda/envs/ocr/`
- **接口**: `/process-pdf/`（POST，上传 PDF 返回结构化 JSON）
- **描述**: 支持基因检测 / 临床生化 / 衰老时钟 / 肠道微生物 / 端粒检测 / 食物过敏 / 营养素等多种类型的 PDF 结构化提取

---

## 8003 — Embedding API

- **框架**: FastAPI + uvicorn
- **进程**: `uvicorn embedding_api:app --host 0.0.0.0 --port 8003`
- **PID**: 9170
- **环境**: `/data/conda/envs/laife-ai/`
- **接口**: `/v1/embeddings`（POST，文本向量化）
- **描述**: 文本 Embedding 向量化接口

---

## 8005 — vLLM 推理服务

- **框架**: vLLM
- **进程**: `vllm serve /data/models/Qwen3.5-4B --port 8005 --tensor-parallel-size 1 --max-model-len 8192 --reasoning-parser qwen3 --language-model-only --enable-prefix-caching --gpu-memory-utilization 0.5 --max-num-seqs 32`
- **PID**: 4165802
- **环境**: `/data/conda/envs/laife-ai/`
- **模型**: Qwen3.5-4B
- **接口**: `/v1/models`、`/tokenize`、OpenAI 兼容 API
- **描述**: 大语言模型推理引擎

---

## 8010 — Health QA Service

- **框架**: FastAPI + uvicorn
- **进程**: `uvicorn main_chat:app --host 0.0.0.0 --port 8010`
- **PID**: 1850712
- **环境**: `/data/conda/envs/laife-ai/`
- **路由**: `chat_personalization_router`、`chat_health_record_router`、`chat_assistant_router`、`chat_followup_router`
- **接口**: `/chat/personalization`、`/chat/health_record` 等
- **描述**: 千人千面健康问答服务，支持 user_id / session_id / report_ids / 知识库等上下文

---

## 8011 — realtime_rag_pipeline API Gateway

- **框架**: 自研 Python 服务
- **进程**: `python main.py serve --config configs/pipeline_preset5.yaml --host 0.0.0.0 --port 8011`
- **PID**: 1385898（用户 wuteng）
- **环境**: `/home/wuteng/.conda/envs/realtime-rag/`
- **接口**: 18 个 API 路径，含 `/metrics`（Prometheus 监控）
- **描述**: 支持人工审核的准实时大语言模型流水线接口

---

## 8012 — ASR Service

- **框架**: FastAPI + uvicorn
- **进程**: `uvicorn main_asr:app --host 0.0.0.0 --port 8012`
- **PID**: 2182797
- **环境**: `/data/conda/envs/laife-ai/`
- **接口**: `/asr/transcribe`、`/asr/transcribe-base64`、`/health`
- **描述**: 语音识别服务（Automatic Speech Recognition）
- **备注**: 刚启动（17:27），此前该端口为空。前端 vite.config.js 仍将 `/chat` 代理到此端口（历史遗留）

---

## 8013 — Report & Sensitive Service

- **框架**: FastAPI + uvicorn
- **进程**: `uvicorn main_report:app --host 0.0.0.0 --port 8013`
- **PID**: 3686722
- **环境**: `/data/conda/envs/laife-ai/`
- **接口**: `/health`、报告相关 CRUD 接口
- **描述**: 报告与敏感信息处理服务

---

## 8014 — Weekly Report Service

- **框架**: FastAPI + uvicorn
- **进程**: `uvicorn main_weekly:app --host 0.0.0.0 --port 8014`
- **PID**: 3458601
- **环境**: `/data/conda/envs/laife-ai/`
- **接口**: `/weekly-report`（GET）
- **描述**: 健康周报生成服务，数据源覆盖 L3 健康档案 + L4 历史咨询摘要 + L5 近 7 天生活事件 + 近 7 天体检报告

---

## 8015 — Questionnaire Service

- **框架**: FastAPI + uvicorn
- **进程**: `uvicorn main_questionnaire:app --host 0.0.0.0 --port 8015`
- **PID**: 482726
- **环境**: `/data/conda/envs/laife-ai/`
- **接口**: `/questionnaire`（POST）
- **描述**: 用户问卷填写记录服务，支持 user_guid / answers / questionnaire_guid 等字段


nohup uvicorn mineru_api:app --host 0.0.0.0 --port 8000 > /dev/null 2>&1 &

nohup uvicorn main_chat:app --host 0.0.0.0 --port 8010 > /dev/null 2>&1 &

nohup uvicorn embedding_api:app --host 0.0.0.0 --port 8003 > /dev/null 2>&1 &

nohup python3 OCR/paddle-ocr.py >/dev/null 2>&1 &

nohup uvicorn main:app --host 0.0.0.0 --port 8002 > /dev/null 2>&1 &

nohup uvicorn main_report:app --host 0.0.0.0 --port 8013 > /dev/null 2>&1 &

nohup uvicorn main_asr:app --host 0.0.0.0 --port 8012 > /dev/null 2>&1 &

nohup uvicorn main_weekly:app --host 0.0.0.0 --port 8014 > /dev/null 2>&1 &

nohup uvicorn main_questionnaire:app --host 0.0.0.0 --port 8015 > /dev/null 2>&1 &

nohup vllm serve /data/models/Qwen3.5-4B \
  --port 8005 \
  --tensor-parallel-size 1 \
  --max-model-len 8192 \
  --reasoning-parser qwen3 \
  --language-model-only \
  --enable-prefix-caching \
  --gpu-memory-utilization 0.5 \
  --max-num-seqs 32 \
  --max-num-batched-tokens 8192 \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder \
  > /dev/null 2>&1 &

8011端口服务：/data/realtime_rag_pipeline
其他服务：/data/laife-ai
