# -*- coding: utf-8 -*-
import logging
from typing import List, Dict, Any

from core.context import Context
from core.registry import registry
from core.state_manager import global_state_manager
from processors.base import BaseProcessor
import processors  # 触发子模块的自动加载 (auto-discovery) 注册所有算子
import time
import uuid

logger = logging.getLogger("PipelineEngine")


class Pipeline:
    """
    数据清洗核心流水线调度引擎。
    负责根据配置实例化的组件数组，驱动 Context 对象不断向下流转。
    """
    def __init__(self, steps_config: List[Dict[str, Any]], pipeline_name: str = "default_pipeline"):
        """
        :param steps_config: 从 yaml 读取的列表，例如:
             [
               {"name": "DeepSeekExtractor", "params": {"model": "chat"}},
               {"name": "BgeEmbedder", "params": {}}
             ]
        :param pipeline_name: 流水线标识，用于构建独立的数据表支持算子热拔插监控
        """
        self.processors: List[BaseProcessor] = []
        self.pipeline_name = pipeline_name
        
        # 动态组装（不导入具体类，全靠魔法注册表）
        processor_names = []
        for step in steps_config:
            processor_name = step.get("name")
            params = step.get("params", {})
            try:
                # 去注册表拿类的指针
                ProcessorClass = registry.get(processor_name)
                # 实例化
                processor_instance = ProcessorClass(**params)
                self.processors.append(processor_instance)
                processor_names.append(processor_name)
                logger.info(f"Loaded processor: {processor_name} with params {params}")
            except Exception as e:
                logger.error(f"Failed to load processor '{processor_name}': {e}")
                raise

        # 同步数据库表结构（热拔插自适应）
        try:
             global_state_manager.sync_table(self.pipeline_name, processor_names)
        except Exception as e:
             logger.warning(f"Failed to sync state table for {self.pipeline_name}: {e}")

    def run(self, context: Context, start_index: int = 0) -> Context:
        """
        执行流水线。按顺序依次调用加载好的 processor。
        支持从某一个特定的 step 恢复执行（如人工审核后继续）。
        """
        # 1. Pipeline Start Tracking Initialization
        if not context.run_id:
            context.run_id = uuid.uuid4().hex
            context.pipeline_name = self.pipeline_name
            
        doc_id = str(context.raw_data.get("id") if isinstance(context.raw_data, dict) else hash(str(context.raw_data)))
        source_file = str(context.metadata.get("input_pdf_path", "")) or str(context.raw_data.get("file_path", "")) if isinstance(context.raw_data, dict) else "unknown"
        
        if start_index == 0:
            global_state_manager.init_run(self.pipeline_name, context.run_id, doc_id, source_file)
            
        final_status = 'completed'

        try:
            for i in range(start_index, len(self.processors)):
                processor = self.processors[i]
                proc_name = processor.__class__.__name__
                # 记录算子执行开始
                global_state_manager.update_step_status(self.pipeline_name, context.run_id, proc_name, 'running')
                
                start_time = time.time()
                # 执行业务逻辑
                try:
                    context = processor.process(context)
                    
                    # 防御性编程：万一某个不规范的 Processor 忘记返回 context
                    if context is None:
                        raise ValueError(f"Processor {processor.__class__.__name__} returned None instead of Context.")
                        
                    step_cost = time.time() - start_time
                    global_state_manager.update_step_status(self.pipeline_name, context.run_id, proc_name, 'success', step_cost)
                        
                except Exception as e:
                    step_cost = time.time() - start_time
                    global_state_manager.update_step_status(self.pipeline_name, context.run_id, proc_name, 'failed', step_cost)
                    
                    # 核心防线：捕获一切未处理异常，确保主进程不崩溃
                    err_msg = f"Fatal error in {processor.__class__.__name__}: {str(e)}"
                    logger.error(err_msg, exc_info=True)  # 记录完整的 traceback 到 errors.log
                    context.mark_invalid(err_msg)
                
                # 【新增】支持半路拦截与人工审核挂起
                if getattr(context, 'is_pending_review', False):
                    context.paused_at_step = i + 1  # 记录断点：下次从下一个算子开始执行
                    logger.info(f"Pipeline paused for human review at step {i} ({processor.__class__.__name__}).")
                    final_status = 'paused'
                    break
                    
                # 如果当前算子觉得数据没救了，标记为 invalid，则提早短路停止
                if not context.is_valid:
                    logger.warning(f"Context marked invalid. Pipeline aborted early. Errors: {context.errors}")
                    final_status = 'failed'
                    break
                    
        except Exception as outer_e:
            final_status = 'failed'
            context.mark_invalid(f"Pipeline Runner Failed: {outer_e}")
            raise
        finally:
            # 最终统一收拢报告总状态 (避免未更新状态导致的盲区)
            global_state_manager.update_global_status(self.pipeline_name, context.run_id, final_status, context.errors)
                
        return context
