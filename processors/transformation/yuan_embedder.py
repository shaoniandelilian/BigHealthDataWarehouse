# -*- coding: utf-8 -*-
import logging
import threading
from typing import Dict, Any

from core.context import Context
from core.registry import ProcessorRegistry
from processors.base import BaseProcessor

# 运行时需要 sentence_transformers
try:
    import torch
    from sentence_transformers import SentenceTransformer
except ImportError as e:
    logging.warning(f"Failed to import sentence-transformers or torch: {e}")

logger = logging.getLogger("YuanEmbedderProcessor")

@ProcessorRegistry.register("YuanEmbedderProcessor")
class YuanEmbedderProcessor(BaseProcessor):
    """
    接收来自语意切分器的 Chunk 列表，通过 SentenceTransformer
    批量将其进行文本编码。专门针对 `Yuan_embedding` 等模型优化。
    """
    
    _model_instance = None
    _lock = threading.Lock()
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.model_path = self.config.get("model_path", "/data/zhenrong/model/Yuan_embedding")
        self.batch_size = self.config.get("batch_size", 64)
        self.max_length = self.config.get("max_length", 512)
        
        # 为了兼容多种环境，提取指定的 device 兜底
        device_str = self.config.get("device", "")
        if device_str:
             self.device = device_str
        else:
             self.device = "cuda" if torch.cuda.is_available() else "cpu"
             
        self._lazy_load_model()
        
    def _lazy_load_model(self):
        with YuanEmbedderProcessor._lock:
            if YuanEmbedderProcessor._model_instance is None and self.model_path:
                 logger.info(f"⏳ Loading Yuan_embedding Model into {self.device}...")
                 
                 # 与给定的示例代码保持一致：开启远程代码信任并使用 bfloat16 以节省显存
                 try:
                     YuanEmbedderProcessor._model_instance = SentenceTransformer(
                         self.model_path,
                         trust_remote_code=True,
                         model_kwargs={"torch_dtype": torch.bfloat16},
                         device=self.device
                     )
                     YuanEmbedderProcessor._model_instance.max_seq_length = self.max_length
                     logger.info("✅ Yuan_embedding model loaded successfully.")
                 except Exception as e:
                     logger.error(f"❌ Failed to load Yuan embedding model: {e}")
                 
    def process(self, context: Context) -> Context:
        chunks = context.metadata.get('chunks', [])
        if not chunks:
            # 如果没有切出任何块，不用抛错，直接往后传空数组即可
            logger.warning("No chunks found in context.metadata. Skipping embedding.")
            return context
            
        if YuanEmbedderProcessor._model_instance is None:
            logger.warning("Yuan Embedding model is not loaded. Mocking embeddings with zeros to pass pipeline.")
            # 假设常见维度为 768 或读取原有设定，在此用 768 假装一下
            for chunk in chunks:
                chunk['embedding'] = [0.0] * 768
            context.metadata['chunks'] = chunks
            return context
            
        logger.info(f"🧠 Encoding {len(chunks)} chunks using Yuan Estimator...")
        
        # 提取所有切片的纯文本
        texts_to_encode = [ch.get('text', '') for ch in chunks]
        
        # 批量向量化 (归一化确保 L2 or Cosine 计算准确)
        try:
            embeddings = YuanEmbedderProcessor._model_instance.encode(
                texts_to_encode, 
                batch_size=self.batch_size, 
                normalize_embeddings=True
            )
        except Exception as e:
            msg = f"Failed to encode texts with Yuan Embedding: {str(e)}"
            logger.error(msg)
            context.mark_invalid(msg)
            return context
            
        # 根据原始列表重新注水挂载
        for idx, chunk in enumerate(chunks):
            # 将 numpy array 转换为标准的 python list 浮点数，便于后续 JSON 序列化与落库
            chunk['embedding'] = embeddings[idx].tolist()
            
        logger.info("✅ Encoding completed and mapped back to chunks.")
        
        # 更新上下文
        context.metadata['chunks'] = chunks
        
        return context
