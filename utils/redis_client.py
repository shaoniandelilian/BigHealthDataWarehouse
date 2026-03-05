# -*- coding: utf-8 -*-
import os
import json
import logging
import time
from typing import Optional, Any

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

logger = logging.getLogger("RedisClient")

class RedisClient:
    """
    Redis 客户端封装，支持缓存、限流等功能。
    如果 Redis 不可用，会自动降级为 Mock 模式，不影响业务主流程。
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(RedisClient, cls).__new__(cls)
        return cls._instance

    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0, password: Optional[str] = None):
        if hasattr(self, 'initialized'):
            return
            
        self.host = os.getenv("REDIS_HOST", host)
        self.port = int(os.getenv("REDIS_PORT", port))
        self.db = int(os.getenv("REDIS_DB", db))
        self.password = os.getenv("REDIS_PASSWORD", password)
        
        self.client = None
        self.mock_cache = {} # --- 新增: 本地内存降级缓存 ---
        self.initialized = True
        
        if REDIS_AVAILABLE:
            try:
                self.client = redis.Redis(
                    host=self.host,
                    port=self.port,
                    db=self.db,
                    password=self.password,
                    socket_connect_timeout=2,
                    decode_responses=True
                )
                # 连一下试试
                self.client.ping()
                logger.info(f"🚀 Redis connected to {self.host}:{self.port}/{self.db}")
            except Exception as e:
                logger.warning(f"⚠️ Redis connection failed: {e}. Falling back to Smart-Mock mode.")
                self.client = None
        else:
            logger.warning("⚠️ Redis library not installed. Falling back to Smart-Mock mode.")

    def get_cache(self, key: str) -> Optional[Any]:
        """获取缓存"""
        if self.client:
            try:
                val = self.client.get(key)
                if val:
                    return json.loads(val)
            except Exception as e:
                logger.error(f"Redis get error: {e}")
        elif key in self.mock_cache:
            return self.mock_cache[key]
        return None

    def set_cache(self, key: str, value: Any, expire_seconds: int = 3600):
        """设置缓存"""
        if self.client:
            try:
                self.client.set(key, json.dumps(value, ensure_ascii=False), ex=expire_seconds)
            except Exception as e:
                logger.error(f"Redis set error: {e}")
        else:
            # 存入本地内存模拟缓存行为
            self.mock_cache[key] = value

    def is_rate_limited(self, key: str, limit: int, window_seconds: int) -> bool:
        """
        基于 Redis 的简单限流 (Fixed Window)
        """
        if not self.client:
            return False
            
        try:
            current = self.client.get(key)
            if current and int(current) >= limit:
                return True
                
            pipe = self.client.pipeline()
            pipe.incr(key)
            # 如果是新键，设置过期时间
            if not current:
                pipe.expire(key, window_seconds)
            pipe.execute()
            return False
        except Exception as e:
            logger.error(f"Redis rate limiting error: {e}")
            return False

# 单例导出
redis_client = RedisClient()
