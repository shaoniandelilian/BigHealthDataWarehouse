# -*- coding: utf-8 -*-
import os
import json
import logging
from typing import Optional, Any, Callable

try:
    from confluent_kafka import Producer, Consumer, KafkaError
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False

logger = logging.getLogger("KafkaManager")

class KafkaManager:
    """
    Kafka 生产者与消费者封装。
    支持优雅降级，如果 Kafka 未配置或不可用，将通过日志报警。
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(KafkaManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, bootstrap_servers: str = "localhost:9092"):
        if hasattr(self, 'initialized'):
            return
            
        self.bootstrap_servers = os.getenv("KAFKA_SERVERS", bootstrap_servers)
        self.producer = None
        self.initialized = True
        
        if KAFKA_AVAILABLE:
            try:
                # 生产者配置
                self.producer = Producer({
                    'bootstrap.servers': self.bootstrap_servers,
                    'client.id': 'chemrag-pipeline-producer',
                    'socket.timeout.ms': 1000,
                })
                logger.info(f"✅ Kafka Producer initialized for {self.bootstrap_servers}")
            except Exception as e:
                logger.warning(f"⚠️ Kafka Producer initialization failed: {e}")
                self.producer = None
        else:
            logger.warning("⚠️ confluent_kafka not installed. Kafka features disabled.")

    def produce(self, topic: str, key: str, value: Any):
        """发送消息到 Topic"""
        if not self.producer:
            return
            
        try:
            payload = json.dumps(value, ensure_ascii=False).encode('utf-8')
            self.producer.produce(topic, key=key, value=payload, callback=self._delivery_report)
            self.producer.flush()
        except Exception as e:
            logger.error(f"Kafka produce error: {e}")

    def _delivery_report(self, err, msg):
        """递送报告回调"""
        if err is not None:
            logger.error(f"❌ Kafka delivery failed: {err}")
        else:
            logger.debug(f"✅ Kafka message delivered to {msg.topic()} [{msg.partition()}]")

    def create_consumer(self, topic: str, group_id: str):
        """创建一个新的消费者"""
        if not KAFKA_AVAILABLE:
            return None
            
        try:
            consumer = Consumer({
                'bootstrap.servers': self.bootstrap_servers,
                'group.id': group_id,
                'auto.offset.reset': 'earliest'
            })
            consumer.subscribe([topic])
            return consumer
        except Exception as e:
            logger.error(f"Kafka consumer creation error: {e}")
            return None

# 单例导出
kafka_manager = KafkaManager()
