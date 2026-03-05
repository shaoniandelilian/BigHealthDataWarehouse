# -*- coding: utf-8 -*-
import logging
from core.context import Context
from core.registry import registry
from processors.base import BaseProcessor

@registry.register("HumanReviewPause")
class HumanReviewPause(BaseProcessor):
    """
    专门用于在管线中间进行拦截的“电子栏杆”算子。
    将此算子配置在 YAML 的中间步骤。当数据流经此地时，
    会被强行打上 is_pending_review = True 的标记，从而导致 Pipeline 暂停循环。
    随后由上层 api_server 负责将其存入本地 SQLite。
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.logger = logging.getLogger("HumanReviewPause")
        self.always_pause = self.config.get("always_pause", True)
        self.use_kafka = self.config.get("use_kafka", False)
        self.kafka_topic = self.config.get("kafka_topic", "chemrag-pending-reviews")

    def process(self, context: Context) -> Context:
        if self.always_pause:
            self.logger.info(f"⏸️ HumanReviewPause hit! Marking context {context.id} as pending review...")
            context.is_pending_review = True
            
            # --- Kafka Integration ---
            if self.use_kafka:
                from utils.kafka_manager import kafka_manager
                self.logger.info(f"📤 Publishing context {context.id} to Kafka topic: {self.kafka_topic}")
                kafka_manager.produce(self.kafka_topic, key=context.id, value=context.to_dict())
            # -------------------------
            
            # --- Metrics ---
            from utils.metrics import PENDING_REVIEWS
            PENDING_REVIEWS.inc()
            # ---------------
            
        return context
