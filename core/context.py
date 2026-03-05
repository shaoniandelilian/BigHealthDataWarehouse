# -*- coding: utf-8 -*-
from typing import Dict, Any, List


class Context:
    """
    数据上下文载体，贯穿整个流水线的节点流转。
    避免组件之间强依赖，所有 Processor 都围绕 Context 进行读写。
    """
    def __init__(self, raw_data: Any = None):
        # 初始脏数据
        self.raw_data = raw_data
        # 结构化抽取出的数据 / 元数据 (例如 compound name, SMILES 等)
        self.metadata: Dict[str, Any] = {}
        # 产出的向量特征
        self.embedding: List[float] = []
        # 管线处理过程中的错误信息与状态
        self.errors: List[str] = []
        self.is_valid: bool = True
        
        # [新增] 支持人工介入审核的挂起状态
        self.is_pending_review: bool = False
        self.paused_at_step: int = -1

    def mark_invalid(self, reason: str):
        """标记当前数据行为无效，并记录原因。可被流水线拦截。"""
        self.is_valid = False
        self.errors.append(reason)
        
    def to_dict(self) -> dict:
        """用于存入数据库序列化"""
        return {
            "raw_data": self.raw_data,
            "metadata": self.metadata,
            "embedding": self.embedding,
            "errors": self.errors,
            "is_valid": self.is_valid,
            "is_pending_review": self.is_pending_review,
            "paused_at_step": self.paused_at_step
        }
        
    @classmethod
    def from_dict(cls, data: dict) -> 'Context':
        """用于从数据库反序列化恢复"""
        ctx = cls(raw_data=data.get("raw_data"))
        ctx.metadata = data.get("metadata", {})
        ctx.embedding = data.get("embedding", [])
        ctx.errors = data.get("errors", [])
        ctx.is_valid = data.get("is_valid", True)
        ctx.is_pending_review = data.get("is_pending_review", False)
        ctx.paused_at_step = data.get("paused_at_step", -1)
        return ctx
