# -*- coding: utf-8 -*-
import json
import logging
import time

import requests

from core.context import Context
from core.registry import registry
from processors.base import BaseProcessor


@registry.register("DeepSeekExtractor")
class DeepSeekExtractor(BaseProcessor):
    """
    负责调用 DeepSeek 大语言模型，从化合物名称中提取 Source 和 Function。
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Security: DO NOT hardcode API keys. Read from environment variables.
        import os
        self.api_key = self.config.get("api_key") or os.environ.get("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("DeepSeekExtractor requires 'DEEPSEEK_API_KEY' environment variable or 'api_key' in config.")
            
        self.api_url = self.config.get("api_url", "https://api.deepseek.com/v1/chat/completions")
        self.model = self.config.get("model", "deepseek-chat")
        self.max_retries = self.config.get("max_retries", 3)
        
        self.logger = logging.getLogger("DeepSeekExtractor")

    def _get_prompt(self, name: str):
        system_prompt = (
            "You are a biomedical knowledge extraction model. Your task is to provide accurate "
            "Source and Function information for chemical compounds based on established biochemical, "
            "pharmacological, and biological knowledge."
        )

        user_prompt = f"""Describe the function and origin of {name} and strictly present the results in the following format:
Source: [Provide detailed source information here]Function: [Provide detailed functional information here]
[Notes]:
1. The response must contain only the Source and Function sections in the specified format.
2. If reliable information is unavailable, use "Not provided".
3. All content must be factually accurate and consistent with established biomedical knowledge.
4. Avoid repeating sentence opening patterns or fixed templates across different compounds.
[Critical Requirements]:
1. The Source section must state only the biological or natural origin...
2. The Function section must be strictly limited to describing its functional role...
3. The output must not contain any markdown formatting symbols such as asterisks (*).
4. The Function section must use definitive statements...
5. When a compound is widely known or clinically used as a drug...
"""
        return system_prompt, user_prompt

    def _call_api_with_retry(self, name: str) -> dict:
        system_prompt, user_prompt = self._get_prompt(name)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.35,
            "max_tokens": 500,
        }

        for attempt in range(1, self.max_retries + 1):
            try:
                # 真实网路请求 (由于长耗时，在真实管道中该 Processor 应该被丢在 Celery 的 MQ 队列执行)
                response = requests.post(self.api_url, headers=headers, json=payload, timeout=35)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                self.logger.warning(f"[{name}] API Call failure attempt {attempt}: {e}")
                time.sleep(2 ** attempt)  # Exponential backoff

        return {"error": "MAX_RETRIES_EXCEEDED"}

    def process(self, context: Context) -> Context:
        # 要求 Context的 raw_data 是一个简单的 compound name (str) 或包含 name 的字典
        name = context.raw_data.get("name") if isinstance(context.raw_data, dict) else str(context.raw_data)
        
        if not name or name == "None":
            context.mark_invalid("Missing compound name for AI extraction.")
            return context

        # --- Redis Cache Logic ---
        from utils.redis_client import redis_client
        cache_key = f"llm_cache:{self.model}:{name}"
        cached_res = redis_client.get_cache(cache_key)
        
        if cached_res:
            self.logger.info(f"🎯 Redis Cache Hit for {name}!")
            context.metadata["deepseek_raw_content"] = cached_res
            context.metadata["is_cached"] = True
            return context
        # -------------------------

        self.logger.info(f"Extracting properties for {name} via DeepSeek...")
        result = self._call_api_with_retry(name)
        
        if "error" in result:
            context.mark_invalid(f"DeepSeek API Error: {result['error']}")
            return context

        # 解析模型返回的结果为 metadata，装箱。
        try:
            content = result["choices"][0]["message"]["content"]
            # 存入 metadata 供下一个节点使用
            context.metadata["deepseek_raw_content"] = content
            
            # --- Save to Redis Cache ---
            redis_client.set_cache(cache_key, content, expire_seconds=86400 * 7) # 缓存一周
            # ---------------------------
        except (KeyError, IndexError):
            context.mark_invalid("Unexpected DeepSeek response format.")

        return context
