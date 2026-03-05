# -*- coding: utf-8 -*-
import json
import logging
import time
import yaml
import os
from utils.kafka_manager import kafka_manager
from core.context import Context
from core.pipeline import Pipeline
from core.review_store import ReviewStore
from utils.logger import setup_logger

logger = setup_logger("KafkaWorker")

def run_worker():
    """
    Kafka 消费者订阅针对 'chemrag-review-completed' Topic。
    当外部系统审核通过后，发消息到该 Topic，Worker 负责唤醒 Pipeline。
    """
    # 加载流水线配置 (同 API Server)
    config_path = os.getenv("PIPELINE_CONFIG", "configs/pipeline_chemicals.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    pipeline_engine = Pipeline(cfg.get("pipeline_steps", []))
    
    # 我们依然需要 ReviewStore 来恢复现场（或者从 Kafka 消息中直接重建）
    review_store = ReviewStore(db_path="logs/pending_reviews.db")
    
    consumer = kafka_manager.create_consumer(
        topic="chemrag-review-completed",
        group_id="chemrag-worker-group"
    )
    
    if not consumer:
        logger.error("Failed to start Kafka Worker: Consumer is None")
        return

    logger.info("🚀 Kafka Worker started. Listening for 'chemrag-review-completed'...")
    
    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                logger.error(f"Consumer error: {msg.error()}")
                continue
                
            try:
                data = json.loads(msg.value().decode('utf-8'))
                context_id = data.get("id")
                updated_payload = data.get("payload", {})
                
                logger.info(f"📩 Received review completion for {context_id}")
                
                # 从本地 Store 或 Kafka 负载恢复 Context
                ctx = review_store.get_and_delete_context(context_id)
                if not ctx:
                    logger.warning(f"Context {context_id} not found in local store. Trying to reconstruct...")
                    # 如果消息里带了全量数据，也可以在这里重建
                    continue
                
                # 合并修改
                if "metadata" in updated_payload:
                    ctx.metadata.update(updated_payload["metadata"])
                
                ctx.is_pending_review = False
                start_idx = ctx.paused_at_step if ctx.paused_at_step > 0 else 0
                
                logger.info(f"▶️ Resuming pipeline for {context_id} at step {start_idx}")
                pipeline_engine.run(ctx, start_index=start_idx)
                logger.info(f"✅ Pipeline completed for {context_id}")
                
            except Exception as e:
                logger.error(f"Error processing Kafka message: {e}")
                
    except KeyboardInterrupt:
        pass
    finally:
        consumer.close()

if __name__ == "__main__":
    run_worker()
