# -*- coding: utf-8 -*-
import logging
from core.context import Context
from core.registry import registry
from processors.base import BaseProcessor
from models.embedder import SimpleBgeEmbeddings


@registry.register("BgeEmbedder")
class BgeEmbedder(BaseProcessor):
    """
    负责调用底层的 SimpleBgeEmbeddings 生成文本特征。
    将 Context 里的目标文本转化为向量并注入回 Context 中。
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        model_path = self.config.get("model_path", "BAAI/bge-large-zh-v1.5")
        local_files_only = self.config.get("local_files_only", False)
        
        self.logger = logging.getLogger("BgeEmbedder")
        self.logger.info(f"Initializing BGE Embedder with model: {model_path}")
        
        # 懒加载或者初始化加载均可，在此为了稳定，放入 __init__ 加载一次
        try:
            self.embedder = SimpleBgeEmbeddings(
                model_name=model_path,
                local_files_only=local_files_only
            )
        except Exception as e:
            self.logger.error(f"Failed to load Embedder: {e}")
            raise

    def process(self, context: Context) -> Context:
        # 自由组合你要嵌顿的文本：可以是原句，也可以是 DeepSeek 提炼出来的 Function
        text_to_embed = context.metadata.get("deepseek_raw_content") or \
                        context.metadata.get("raw_smiles") or \
                        str(context.raw_data)
        
        if not text_to_embed or text_to_embed == "None":
            context.mark_invalid("No valid text found to embed.")
            return context
            
        self.logger.info(f"Embedding text snapshot: {text_to_embed[:30]}...")
        
        try:
            vector = self.embedder.embed_query(text_to_embed)
            if not vector:
                context.mark_invalid("Embedder returned empty vector.")
                return context
                
            # 将产生的向量附着到被流转的装箱数据 Context 上
            context.embedding = vector
            self.logger.info("Embedded text successfully.")
        except Exception as e:
            context.mark_invalid(f"Embedding failed: {str(e)}")
            
        return context
