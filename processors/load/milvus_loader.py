# -*- coding: utf-8 -*-
import logging
from pymilvus import connections, Collection

from core.context import Context
from core.registry import registry
from processors.base import BaseProcessor

@registry.register("MilvusLoader")
class MilvusLoader(BaseProcessor):
    """
    负责将最终的特征向量和 Metadata 落库至 Milvus。
    等价于之前的 import_to_milvus.py
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.host = self.config.get("host", "127.0.0.1")
        self.port = self.config.get("port", "19530")
        self.collection_name = self.config.get("collection")
        
        self.logger = logging.getLogger("MilvusLoader")
        
        if not self.collection_name:
            raise ValueError("MilvusLoader requires a 'collection' name parameter.")

        # 全局常驻链接
        try:
            connections.connect(alias="default", host=self.host, port=self.port)
            from pymilvus import utility, FieldSchema, CollectionSchema, DataType
            
            # 如果远端库不存在这个采集表，自动新建装配
            if not utility.has_collection(self.collection_name):
                self.logger.info(f"Collection '{self.collection_name}' not found. Auto-creating schema...")
                dim = self.config.get("dimension", 1024)
                
                fields = [
                    FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=100),
                    FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=500),
                    FieldSchema(name="header_path", dtype=DataType.VARCHAR, max_length=200),
                    FieldSchema(name="data_type", dtype=DataType.VARCHAR, max_length=50),
                    FieldSchema(name="chunk_length", dtype=DataType.INT64),
                    FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=8000),
                    FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dim)
                ]
                schema = CollectionSchema(fields, f"Auto-generated collection for {self.collection_name}")
                self.coll = Collection(name=self.collection_name, schema=schema)
                
                # 创建默认内积搜索索引 (Inner Product suitable for normalized BGE vectors)
                index_params = {
                    "metric_type": "IP", 
                    "index_type": "IVF_FLAT",
                    "params": {"nlist": 128}
                }
                self.coll.create_index(field_name="embedding", index_params=index_params)
                self.logger.info(f"✅ Created and indexed new collection '{self.collection_name}'.")
            else:
                self.coll = Collection(self.collection_name)
                
            self.coll.load()
            self.logger.info(f"✅ Connected to Milvus and loaded collection: {self.collection_name}")
        except Exception as e:
            self.logger.error(f"Failed to initialize Milvus connection or schema: {e}")
            self.coll = None

    def process(self, context: Context) -> Context:
        if not context.embedding:
            context.mark_invalid("Cannot load to Milvus: Context has no embedding.")
            return context

        if not getattr(self, "coll", None):
             context.mark_invalid("Milvus connection not established or collection missing.")
             return context

        # 构造一条要存入的数据实体结构 (需要与您实际 Milvus 的 Schema 对齐)
        # 例如: [ids, sources, header_paths, data_types, chunk_lengths, texts, embs]
        try:
            # 自动生成个假 ID
            import uuid
            row_id = str(uuid.uuid4())
            text_desc = context.metadata.get("deepseek_raw_content", "None")[:4000]
            smiles = context.metadata.get("Standardized_SMILES", "")
            
            entities = [
                [row_id],            # ids
                [smiles],            # sources -> 作为smiles存放点
                ["realtime_rag"],    # header_paths
                ["molecule_info"],   # data_types
                [len(text_desc)],    # chunk_lengths
                [text_desc],         # texts
                [context.embedding]  # embs
            ]
            
            self.coll.insert(entities)
            self.logger.info(f"Successfully inserted vector into Milvus collection '{self.collection_name}'.")
        except Exception as e:
            context.mark_invalid(f"Milvus insert failed: {str(e)}")

        return context
