#!/bin/bash
set -e
source /opt/laife/envs/vllm/bin/activate
exec vllm serve /opt/laife/models/Qwen3.5-4B \
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
  --tool-call-parser qwen3_coder
