# GPU 显存预算（单卡 L20 48GB）

| 服务 | 配置值 | 实测占用 | 基线日期 |
|---|---|---|---|
| vLLM 8005 | gpu-memory-utilization 0.50 | 24 GB | <部署日> |
| ASR 8012 | ASR_VLLM_GPU_MEMORY_UTILIZATION 0.13 | 6 GB | <部署日> |
| MinerU 8000 | （峰值） | ~7 GB | <部署日> |
| PaddleOCR 8001 | use_gpu=True | ~4 GB | <部署日> |
| Embedding 8003 | gpu_mem_limit=2 GB | 2 GB | <部署日> |
| **合计** | — | **~43 GB / 48 GB (~90%)** | — |

## 调整规则
- 任何服务调高 gpu_memory_utilization 之前必须更新此表
- 任何新服务上线前必须评估显存并在此表登记
