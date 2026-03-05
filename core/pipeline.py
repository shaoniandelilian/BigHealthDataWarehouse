# -*- coding: utf-8 -*-
import logging
from typing import List, Dict, Any

from core.context import Context
from core.registry import registry
from processors.base import BaseProcessor
import processors  # 触发子模块的自动加载 (auto-discovery) 注册所有算子

logger = logging.getLogger("PipelineEngine")


class Pipeline:
    """
    数据清洗核心流水线调度引擎。
    负责根据配置实例化的组件数组，驱动 Context 对象不断向下流转。
    """
    def __init__(self, steps_config: List[Dict[str, Any]]):
        """
        :param steps_config: 从 yaml 读取的列表，例如:
             [
               {"name": "DeepSeekExtractor", "params": {"model": "chat"}},
               {"name": "BgeEmbedder", "params": {}}
             ]
        """
        self.processors: List[BaseProcessor] = []
        
        # 动态组装（不导入具体类，全靠魔法注册表）
        for step in steps_config:
            processor_name = step.get("name")
            params = step.get("params", {})
            try:
                # 去注册表拿类的指针
                ProcessorClass = registry.get(processor_name)
                # 实例化
                processor_instance = ProcessorClass(**params)
                self.processors.append(processor_instance)
                logger.info(f"Loaded processor: {processor_name} with params {params}")
            except Exception as e:
                logger.error(f"Failed to load processor '{processor_name}': {e}")
                raise

    def run(self, context: Context, start_index: int = 0) -> Context:
        """
        执行流水线。按顺序依次调用加载好的 processor。
        支持从某一个特定的 step 恢复执行（如人工审核后继续）。
        """
        for i in range(start_index, len(self.processors)):
            processor = self.processors[i]
            # 执行业务逻辑
            try:
                context = processor.process(context)
                
                # 防御性编程：万一某个不规范的 Processor 忘记返回 context
                if context is None:
                    raise ValueError(f"Processor {processor.__class__.__name__} returned None instead of Context.")
                    
            except Exception as e:
                # 核心防线：捕获一切未处理异常，确保主进程不崩溃
                err_msg = f"Fatal error in {processor.__class__.__name__}: {str(e)}"
                logger.error(err_msg, exc_info=True)  # 记录完整的 traceback 到 errors.log
                context.mark_invalid(err_msg)
            
            # 【新增】支持半路拦截与人工审核挂起
            if getattr(context, 'is_pending_review', False):
                context.paused_at_step = i + 1  # 记录断点：下次从下一个算子开始执行
                logger.info(f"Pipeline paused for human review at step {i} ({processor.__class__.__name__}).")
                break
                
            # 如果当前算子觉得数据没救了，标记为 invalid，则提早短路停止
            if not context.is_valid:
                logger.warning(f"Context marked invalid. Pipeline aborted early. Errors: {context.errors}")
                break
                
        return context
