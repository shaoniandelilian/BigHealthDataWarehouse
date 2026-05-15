# Laife 裸机部署包 v1.0

## 使用方法

### 1. 前置条件
确保目标服务器满足以下条件（见 DEPLOYMENT.md §1）：
- Ubuntu 22.04 LTS
- NVIDIA GPU（≥40GB 显存）
- root 权限
- 能 SSH 到旧服务器 `47.98.227.81`（用于 rsync 模型）
- MongoDB（:8060）、PostgreSQL（:8070）、Milvus（:8050）已就绪
- 所有 API Key 已准备好

### 2. 部署步骤

```bash
# 将本部署包 scp 到目标服务器
scp -r deploy-bundle/ root@<目标服务器>:/root/deploy-bundle/

# SSH 到目标服务器
ssh root@<目标服务器>

# 进入部署包目录
cd /root/deploy-bundle

# 修改 deploy.sh 开头的 Git 仓库地址（如有需要）
# vi deploy.sh

# 执行部署
bash deploy.sh
```

脚本会按 Task 1-12 + Phase F 顺序执行，每完成一个 Task 暂停等待确认。

### 3. 中途中断恢复

```bash
# 如果 Phase A 已完成但重启后断了
bash deploy.sh --from-phase-b

# 如果只是某个 Task 失败，修好后重新执行该脚本会自动跳过已完成步骤
```

### 4. 部署包文件清单

```
deploy-bundle/
├── deploy.sh                  # 主编排脚本（按 Task 顺序执行全部步骤）
├── README.md                  # 本文件
├── bin/                       # 所有服务启动脚本（部署到 /opt/laife/bin/）
│   ├── launch-vllm.sh         # Task 4: vLLM 8005
│   ├── launch-questionnaire.sh # Task 5: Questionnaire 8015
│   ├── launch-weekly.sh       # Task 5: Weekly Report 8014
│   ├── launch-embedding.sh    # Task 6: Embedding 8003
│   ├── launch-mineru.sh       # Task 7: MinerU 8000
│   ├── launch-paddle-ocr.sh   # Task 8: PaddleOCR 8001
│   ├── launch-pdf-extract.sh  # Task 9: PDF Extract 8002
│   ├── launch-chat.sh         # Task 10: Health QA 8010
│   ├── launch-report.sh       # Task 10: Report 8013
│   ├── launch-asr.sh          # Task 10: ASR 8012
│   ├── launch-rag-api.sh      # Task 11: RAG API 8011
│   ├── launch-rag-worker.sh   # Task 11: RAG Worker
│   ├── healthcheck.sh         # Task 12: 全服务健康检查
│   └── rollout.sh             # Task 12: 滚动重启
├── config/
│   ├── services.env           # 非敏感配置（含占位符）
│   ├── secrets.env            # 敏感配置模板（需填入实际值）
│   └── logrotate-laife        # logrotate 配置
├── systemd/
│   ├── laife@.service         # CPU 服务 systemd 模板
│   ├── laife-gpu@.service     # GPU 服务 systemd 模板
│   └── laife-rag@.service     # RAG 服务 systemd 模板
└── docs/
    ├── GPU_BUDGET.md          # GPU 显存预算表
    └── RUNBOOK.md             # 运维手册
```

## 代码修改说明

Task 2 的 7 处代码修改已在本部署包中预设。如果你已经将修改合并到 Git 仓库的主分支，
`deploy.sh` 会跳过 patch 步骤。否则脚本会自动用 sed 执行修改。

修改清单：
1. `OCR/utils.py` — 删除 `CUDA_VISIBLE_DEVICES` 硬编码
2. `OCR/utils.py` — `MINERU_TOOLS_CONFIG_JSON` 路径 env 化
3. `OCR/utils.py` — PaddleOCR URL 从 env 读
4. `OCR/paddle-ocr.py` — 模型路径从 env 读
5. `OCR/mineru_api.py` — 默认 mineru.json 路径改为 `/opt/laife/config/`
6. `configs/pipeline_preset5.yaml` + `multi_llm_filter.py` — API key 占位符 + env 展开
7. `streaming/api_server.py` — 数据路径 env 化

## 安全说明

- `secrets.env` 包含 API Key，部署后权限为 `640 root:laife`
- 不要在终端中回显 secrets.env 内容
- 不要在 Git 中提交 `.env` / `secrets.env`
