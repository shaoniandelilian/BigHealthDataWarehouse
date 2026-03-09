# -*- coding: utf-8 -*-
import uuid
import logging
from typing import Dict, Any

from core.context import Context
from core.registry import ProcessorRegistry
from processors.base import BaseProcessor

try:
    from pymilvus import connections, FieldSchema, CollectionSchema, DataType, Collection, utility
except ImportError as e:
    logging.warning(f"PyMilvus is not installed. MilvusTypeLoader will crash if triggered: {e}")

logger = logging.getLogger("MilvusTypeLoader")

# 硬性规定参数
MAX_TEXT_LEN = 32768
MAX_TYPE_LEN = 256

@ProcessorRegistry.register("MilvusTypeLoader")
class MilvusTypeLoader(BaseProcessor):
    """
    将带有 Embedding 的 Chunks 数组落盘至 Milvus 的专门加载器。
    满足复杂的表结构要求： pk, id_1, type, text, embedding。
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.host = self.config.get("host", "127.0.0.1")
        self.port = str(self.config.get("port", "19530"))
        self.collection_name = self.config.get("collection", "default_docs")
        self.batch_size = self.config.get("batch_size", 500)
        
        # 动态检测连接是否可用，只警告不立刻抛出（因为本组件是在导入时注册的，防止应用主进程挂掉）
        self._connect_milvus()
        self.collection_instance = None
        
    def _connect_milvus(self):
        try:
            # Pymilvus 的全局连接池注册
            connections.connect(alias="default", host=self.host, port=self.port)
            logger.info(f"✅ Connected to Milvus Service {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"❌ Failed to connect to Milvus: {e}")
            

    def _prepare_collection(self, embedding_dim: int):
        """
        初始化集合，若不存在则创建。Schema 匹配现有 test_wuji 的 7 字段结构。
        """
        if self.collection_instance:
             return self.collection_instance
             
        if not utility.has_collection(self.collection_name):
            logger.info(f"🆕 Creating Milvus Collection: {self.collection_name} (dim: {embedding_dim})")
            fields = [
                FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=100, is_primary=True),
                FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=500),
                FieldSchema(name="header_path", dtype=DataType.VARCHAR, max_length=200),
                FieldSchema(name="data_type", dtype=DataType.VARCHAR, max_length=50),
                FieldSchema(name="chunk_length", dtype=DataType.INT64),
                FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=8000),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=embedding_dim)
            ]
            schema = CollectionSchema(fields=fields, description="Realtime Pipeline Chunks")
            collection = Collection(name=self.collection_name, schema=schema)

            collection.create_index(
                field_name="embedding", 
                index_params={
                    "index_type": "HNSW",
                    "metric_type": "COSINE",
                    "params": {"M": 16, "efConstruction": 200}
                }
            )
            logger.info("✅ Collection and indexes created.")
            self.collection_instance = collection
        else:
            logger.info(f"📦 Using existing Collection: {self.collection_name}")
            self.collection_instance = Collection(self.collection_name)
            
        self.collection_instance.load()
        return self.collection_instance

    def process(self, context: Context) -> Context:
        try:
            if not connections.has_connection("default"):
               self._connect_milvus()
               
            if not connections.has_connection("default"):
               logger.warning("No active connection to Milvus, cannot insert chunks. Proceeding without error.")
               return context
        except Exception as e:
            logger.warning(f"Milvus connection check failed: {e}. Proceeding without error.")
            return context

        chunks = context.metadata.get('chunks', [])
        
        if not chunks:
            logger.warning("No chunks to insert. Skipping Milvus push.")
            return context
            
        first_emb = chunks[0].get('embedding')
        if not first_emb:
            context.mark_invalid("Chunks missing 'embedding' field. Check YuanEmbedderProcessor.")
            return context
        
        emb_dim = len(first_emb)
        collection = self._prepare_collection(emb_dim)
        
        logger.info(f"📥 Flushing {len(chunks)} fragments to Milvus...")
        
        # 匹配现有 Schema 的 7 个字段
        col_ids = []
        col_sources = []
        col_header_paths = []
        col_data_types = []
        col_chunk_lengths = []
        col_texts = []
        col_embeddings = []
        
        inserted_count = 0
        source_name = context.metadata.get("source_filename", "unknown")
        
        for i, chunk in enumerate(chunks, 1):
             text = chunk.get('text', '')
             if not text:
                  continue
                  
             safe_text = text[:8000]
             meta = chunk.get('metadata', {}) or {}
             header_path = meta.get("header_path", "")[:200]
             data_type = meta.get("type", "document_ai_chunk")[:50]
             
             # 生成唯一 ID: source_chunkIndex_uuid (防止主键冲突)
             chunk_id = f"{source_name}_{i}_{uuid.uuid4().hex[:8]}"[:100]
             
             col_ids.append(chunk_id)
             col_sources.append(str(source_name)[:500])
             col_header_paths.append(header_path)
             col_data_types.append(data_type)
             col_chunk_lengths.append(len(text))
             col_texts.append(safe_text)
             col_embeddings.append(chunk.get('embedding'))
             inserted_count += 1
             
             if len(col_texts) >= self.batch_size:
                 collection.insert([col_ids, col_sources, col_header_paths, col_data_types, col_chunk_lengths, col_texts, col_embeddings])
                 col_ids.clear(); col_sources.clear(); col_header_paths.clear()
                 col_data_types.clear(); col_chunk_lengths.clear()
                 col_texts.clear(); col_embeddings.clear()
                  
        # 扫尾剩余
        if col_texts:
            collection.insert([col_ids, col_sources, col_header_paths, col_data_types, col_chunk_lengths, col_texts, col_embeddings])
            
        collection.flush()
        logger.info(f"🎉 Success! Inserted {inserted_count} vector rows to Milvus.")
        
        context.metadata["milvus_inserted_count"] = inserted_count
        return context
