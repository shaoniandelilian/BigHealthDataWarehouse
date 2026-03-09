# -*- coding: utf-8 -*-
"""
FastAPI Streaming Gateway (HTTP Webhook)
让整个 Pipeline 流水线变成一个常驻后台的 API 服务。
任何外部脚本、爬虫、业务系统只要向这个接口发送 POST 请求，
就可以立刻触发一条数据的端到端清洗与入库。
"""
import os
import logging
import yaml
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Dict, Any, Optional

from core.context import Context
from core.pipeline import Pipeline
from core.review_store import ReviewStore
from utils.logger import setup_logger

logger = setup_logger("APIServer")

# 1. 初始化 FastAPI 应用
app = FastAPI(
    title="ChemRAG-Flow API Gateway v2",
    description="支持人工审核 (Human-in-the-Loop) 的准实时大语言模型流水线接口",
    version="2.0.0"
)

# 保证本地日志文件夹存在，用于存储 SQLite DB
os.makedirs("logs", exist_ok=True)
review_store = ReviewStore(db_path="logs/pending_reviews.db")

# 2. 全局加载 Pipeline 实例
try:
    # 支持通过环境变量动态指定要跑哪条流水线（化学生成 vs PDF解析）
    config_path = os.getenv("PIPELINE_CONFIG", "configs/pipeline_chemicals.yaml")
    logger.info(f"API Server: Loading pipeline configuration from {config_path}")
    
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    pipeline_name = os.path.basename(config_path)
    pipeline_engine = Pipeline(cfg.get("pipeline_steps", []), pipeline_name=pipeline_name)
    logger.info("API Server: Pipeline engine pre-loaded successfully.")
except Exception as e:
    logger.error(f"Failed to initialize Pipeline from {config_path}: {e}")
    raise RuntimeError("Cannot start API server without a valid pipeline configuration.")

# 3. 定义外部请求的数据契约 (Schema)
class DocumentEvent(BaseModel):
    """外部应用发过来的单条实体数据格式范例"""
    id: str
    name: Optional[str] = None
    raw_smiles: Optional[str] = None
    raw_selfies: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = {}
    raw_data: Optional[Dict[str, Any]] = {}

class ReviewSubmit(BaseModel):
    """人工审核回传修改过的数据"""
    raw_data: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    chunks_override: Optional[Dict[int, str]] = None # 用于单点覆盖 chunk: {0: "修好后的文本", 1: "..."}

def _handle_pipeline_result(event_id: str, final_ctx: Context) -> dict:
    """内部通用函数，处理流水线跑完后的三个出口：通过、挂起待审、报错"""
    if getattr(final_ctx, 'is_pending_review', False):
        review_store.save_pending_context(event_id, final_ctx)
        return {
            "status": "pending_review",
            "message": "Data requires human review. Saved to pending queue.",
            "id": event_id
        }
    elif final_ctx.is_valid:
        return {
            "status": "success", 
            "message": "Data processed and stored successfully.",
            "id": event_id,
            "metadata_snapshot": final_ctx.metadata
        }
    else:
        # 如果不是后台任务，这个会抛错返回 400
        return {"status": "error", "errors": final_ctx.errors}

def process_event_background(event: DocumentEvent):
    """【异步引擎】后台线程里慢吞吞跑"""
    raw_data = event.model_dump()
    ctx = Context(raw_data=raw_data)
    if event.metadata:
         ctx.metadata.update(event.metadata)
         
    try:
        final_ctx = pipeline_engine.run(ctx)
        result = _handle_pipeline_result(event.id, final_ctx)
        if result["status"] == "success":
            logger.info(f"✅ Background job for '{event.id}' completed successfully.")
        elif result["status"] == "pending_review":
            logger.info(f"⏸️ Background job for '{event.id}' paused for manual review.")
        else:
            logger.warning(f"❌ Background job for '{event.id}' failed. Errors: {result.get('errors')}")
    except Exception as e:
        logger.error(f"🔥 Catastrophic failure in background job {event.id}: {e}")

# ==================== 监控与可观测性 ====================
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response
from utils.metrics import PIPELINE_TOTAL, PROCESSOR_LATENCY

@app.get("/metrics")
def metrics():
    """导出 Prometheus 监控指标"""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

# ==================== 标准入库接口 ====================

@app.post("/api/v1/ingest/sync")
def ingest_document_sync(event: DocumentEvent):
    """
    【同步接口】: 一直卡住直到流水线出结果（或被挂起审核）。
    """
    with PROCESSOR_LATENCY.labels(processor_name="full_pipeline_sync").time():
        logger.info(f"Received sync ingestion request for id: {event.id}")
        raw_data = event.model_dump()
        ctx = Context(raw_data=raw_data)
        if event.metadata:
            ctx.metadata.update(event.metadata)
            
        final_ctx = pipeline_engine.run(ctx)
        result = _handle_pipeline_result(event.id, final_ctx)
        
        # 埋点记录
        PIPELINE_TOTAL.labels(pipeline_type="chemicals", status=result["status"]).inc()
        
        if result["status"] == "error":
            raise HTTPException(status_code=400, detail=result)
            
        return result

@app.post("/api/v1/ingest/async")
def ingest_document_async(event: DocumentEvent, background_tasks: BackgroundTasks):
    """
    【异步接口】: 接口秒回 OK，复杂的提取丢到后台，随后可以通过审核接口检视。
    """
    logger.info(f"Received async ingestion request for id: {event.id}")
    PIPELINE_TOTAL.labels(pipeline_type="chemicals", status="accepted").inc()
    background_tasks.add_task(process_event_background, event)
    return {"status": "accepted", "message": "Pipeline processing started in background."}

# ==================== API 人工审核专用接口 ====================

@app.post("/api/v1/review/chunks/{context_id}")
def submit_chunk_review_sync(context_id: str, submission: ReviewSubmit):
    """
    【切片级审核专用接口】: 针对被 `ChunkLevelReviewPause` 拦下的特定不确定片段进行人工重写覆盖。
    submission.chunks_override 示例: {"12": "这句人工优化过了", "45": "另一个句子"}
    提交后自动清除这些片段的 is_uncertain 标志，如果所有片段都已审毕，则放通流水线往下执行。
    """
    logger.info(f"Received chunk-level review override for id: {context_id}")
    
    ctx = review_store.get_and_delete_context(context_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="Context not found or already submitted/deleted in DB.")
        
    if not submission.chunks_override:
         raise HTTPException(status_code=400, detail="Missing chunks_override data in payload.")
         
    chunks = ctx.metadata.get("chunks", [])
    
    # 覆盖人工提供的所有文本
    for idx_str, new_text in submission.chunks_override.items():
        try:
            idx = int(idx_str)
            if 0 <= idx < len(chunks):
                chunks[idx]["text"] = new_text
                chunks[idx]["is_uncertain"] = False # 已解除威胁
        except ValueError:
            pass
            
    # 复查：是否还有剩余的 “不确定切片” 没被覆盖？
    remaining_uncertain = [i for i, c in enumerate(chunks) if c.get("is_uncertain", False)]
    if remaining_uncertain:
        # 还有未解决的疑虑切片，重新冻结它
        logger.info(f"Pending chunks remaining {remaining_uncertain}. Re-freezing context {context_id}.")
        review_store.save_pending_context(context_id, ctx)
        return {
            "status": "pending_review",
            "message": f"Updated chunks. However, there are still remaining uncertain chunks: {remaining_uncertain}",
            "id": context_id
        }
    
    logger.info("All uncertain chunks resolved! Proceeding with pipeline embedder layer...")
    ctx.is_pending_review = False
    start_idx = ctx.paused_at_step if ctx.paused_at_step > 0 else 0
    final_ctx = pipeline_engine.run(ctx, start_index=start_idx)
    
    result = _handle_pipeline_result(context_id, final_ctx)
    if result["status"] == "error":
         raise HTTPException(status_code=400, detail=result)
    return result

@app.get("/api/v1/review/pending")
def get_pending_reviews(limit: int = 50):
    """
    【审核接口 1】获取队列中所有被 "HumanReviewPause" 锁住等待人工审核的数据。
    """
    records = review_store.get_pending_records(limit=limit)
    return {
        "status": "success",
        "count": len(records),
        "data": records
    }

@app.post("/api/v1/review/submit/{context_id}")
def submit_review_sync(context_id: str, submission: ReviewSubmit):
    """
    【审核接口 2】人员完成审核/修改后，将数据合并回原 Context，并恢复后半段 Pipeline 执行。
    """
    logger.info(f"Received review submission for id: {context_id}")
    # 1. 把压在 SQLite 里的原始 Context 挖出来
    ctx = review_store.get_and_delete_context(context_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="Context not found or already submitted/deleted.")
        
    # 2. 合并人工订正产生的新数据修改
    if submission.raw_data:
        # 如果 raw_data 是字典，选择性更新
        if isinstance(ctx.raw_data, dict):
            ctx.raw_data.update(submission.raw_data)
        else:
            ctx.raw_data = submission.raw_data
    if submission.metadata:
        ctx.metadata.update(submission.metadata)
        
    # 3. 将锁定状态清楚，计算从第几步恢复
    ctx.is_pending_review = False
    start_idx = ctx.paused_at_step if ctx.paused_at_step > 0 else 0
    
    logger.info(f"Resuming pipeline for context {context_id} at step {start_idx}...")
    
    # 4. 继续驱动流水线
    final_ctx = pipeline_engine.run(ctx, start_index=start_idx)
    result = _handle_pipeline_result(context_id, final_ctx)
    
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result)
        
    return result

@app.get("/health")
def health_check():
    """检测服务存活状态"""
    return {"status": "ok", "service": "ChemRAG-Flow Pipeline Gateway API"}

if __name__ == "__main__":
    import uvicorn
    # 本地开发测试启动命令：python streaming/api_server.py
    logger.info("Starting Uvicorn Server on http://0.0.0.0:8000")
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)
