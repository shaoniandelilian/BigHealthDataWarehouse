# -*- coding: utf-8 -*-
import logging
from core.context import Context
from core.registry import registry
from processors.base import BaseProcessor

@registry.register("ChunkLevelReviewPause")
class ChunkLevelReviewPause(BaseProcessor):
    """
    文档切片级别的人工审核拦截器 (Chunk-Level Human-in-the-loop)。
    放置于 LLMChunkReviewer 之后。
    它会扫描 context.metadata['chunks'] 中所有的 chunk，
    是否存在被上游标记为 `is_uncertain = True` 的切片。
    如果有，则拦截并挂起当前流水线上下文，等待人工调用 API 修复这些特定切片。
    如果没有，则无感放行，直接进入 Embedder。
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.logger = logging.getLogger("ChunkLevelReviewPause")

    def process(self, context: Context) -> Context:
        chunks = context.metadata.get("chunks", [])
        uncertain_chunks_idx = []
        
        # 扫描并收集所有处于“不确定”状态的切片索引
        for i, chunk in enumerate(chunks):
            if chunk.get("is_uncertain", False):
                uncertain_chunks_idx.append(i)
                
        if uncertain_chunks_idx:
            self.logger.info(f"⏸️ ChunkLevelReviewPause hit! Found {len(uncertain_chunks_idx)} uncertain chunks: {uncertain_chunks_idx}. Pausing pipeline...")
            
            # 向下文对象注入专门的待审视列表元数据，方便前端/API渲染
            context.metadata["pending_uncertain_chunks"] = uncertain_chunks_idx
            
            # 打上全局暂停 Tag，通知 pipeline runner 退避
            context.is_pending_review = True
            
            # Metrics (可选)
            try:
                from utils.metrics import PENDING_REVIEWS
                PENDING_REVIEWS.inc()
            except ImportError:
                pass
        else:
            self.logger.info("⏩ No uncertain chunks found. Pipeline running smoothly.")
            
        return context
