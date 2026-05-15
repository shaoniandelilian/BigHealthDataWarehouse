# Laife 运维手册

## 启动顺序（机器重启后）
systemd 已经用 After= 声明依赖，`reboot` 后会自动按序启动，大约需要 5 分钟。
人工检查顺序：
1. laife-gpu@vllm（最慢，3 min）
2. laife-gpu@{mineru,paddle-ocr,embedding,asr}（并行，各 30-60s）
3. laife@{pdf-extract,chat,report,weekly,questionnaire}
4. laife-rag@{api,worker}

## 全量重启

for svc in $(systemctl list-units 'laife*' --type=service --no-legend | awk '{print $1}'); do
  sudo systemctl restart "$svc"
  sleep 5
done
/opt/laife/bin/healthcheck.sh

## 常见故障

### vLLM OOM
症状：journalctl 里看到 `CUDA out of memory`
排查：`nvidia-smi` 看谁在吃显存；大概率是 ASR 的 utilization 被调高了
修：把 ASR_VLLM_GPU_MEMORY_UTILIZATION 调回 0.13，重启 asr

### MinerU 启动失败
症状：`AttributeError: 'NoneType' object has no attribute 'get'`
排查：`ls /opt/laife/config/mineru.json`
修：从旧机 scp 回来

### Mongo/PG 连接失败
症状：motor / asyncpg 报连接超时
排查：`nc -vz <host> <port>`
修：检查防火墙规则

### 8010 Chat 启动慢
现象：systemctl status 显示 activating 超过 30 秒
原因：import 链 36 个文件 + sentence_transformers + pymilvus 加载
解：耐心等，第一次启动大约 45-60 秒属正常

## 回退流程
新服务器故障 → DNS / 前端网关切回旧服务器 47.98.227.81；
数据库和 Milvus 未迁移，两个服务器的业务状态不会冲突。

## 发布流程
`/opt/laife/bin/rollout.sh <service>`，参数是 systemd 模板 `%i`，例如：
- `rollout.sh chat` 重启 8010
- `rollout.sh mineru` 重启 8000
- `rollout.sh rag-api` 重启 8011 API
- `rollout.sh rag-worker` 重启 8011 Worker
