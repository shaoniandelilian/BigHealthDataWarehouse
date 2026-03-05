# -*- coding: utf-8 -*-
from prometheus_client import Counter, Histogram, Gauge, Summary

# 1. 吞吐量指标
PIPELINE_TOTAL = Counter(
    "chemrag_pipeline_processed_total",
    "Total number of documents processed by the pipeline",
    ["pipeline_type", "status"]
)

# 2. 耗时指标
PROCESSOR_LATENCY = Histogram(
    "chemrag_processor_duration_seconds",
    "Latency of individual processors in seconds",
    ["processor_name"]
)

# 3. 缓存命中率
CACHE_HITS = Counter(
    "chemrag_cache_hits_total",
    "Total number of cache hits in the pipeline",
    ["cache_type"]
)

# 4. 系统负载 (示例: 待审核任务数)
PENDING_REVIEWS = Gauge(
    "chemrag_pending_reviews_count",
    "Current number of documents waiting for human review"
)

# 5. LLM Token 消耗或调用计数
LLM_CALLS = Counter(
    "chemrag_llm_api_calls_total",
    "Total number of LLM API calls made",
    ["model", "result"]
)
