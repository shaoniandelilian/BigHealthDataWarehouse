# -*- coding: utf-8 -*-
import os
import time
import logging
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from core.context import Context
from core.registry import ProcessorRegistry
from processors.base import BaseProcessor

logger = logging.getLogger("LLMChunkReviewerProcessor")

@ProcessorRegistry.register("LLMChunkReviewerProcessor")
class LLMChunkReviewerProcessor(BaseProcessor):
    """
    接收 SemanticChunker 生成的 chunks 数组。
    针对每一个 chunk，利用 DeepSeek（或其他 LLM）进行并发审核与润色。
    如果大模型返回指定的拒绝词（如 [REJECT]），则将该 chunk 丢弃。
    否则，将大模型返回的润色文本替换原 chunk 的文本内容。
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.api_key = self.config.get("api_key") or os.environ.get("DEEPSEEK_API_KEY")
            
        self.api_url = self.config.get("api_url", "https://api.deepseek.com/v1/chat/completions")
        self.model = self.config.get("model", "deepseek-chat")
        
        # 允许外部通过 yaml 配置 prompt，提供默认的 Prompt
        self.system_prompt = self.config.get(
            "system_prompt", 
            "You are a strict data quality auditor and text editor. Your job is to review OCR-extracted document chunks."
        )
        self.user_prompt_template = self.config.get(
            "user_prompt_template", 
            "Evaluate the following text chunk. If it contains less than 50% coherent sentences, is purely menu navigation, or is mostly garbage characters, reply exactly with '[REJECT]'. Otherwise, fix any OCR typos, improve readability without altering the original meaning, and output ONLY the corrected text.\n\nText:\n{text}"
        )
        
        self.max_workers = self.config.get("max_workers", 5) # 并发数
        self.max_retries = self.config.get("max_retries", 3)
        self.timeout = self.config.get("timeout", 45)

    def _review_single_chunk(self, chunk: Dict[str, Any], index: int) -> Dict[str, Any]:
        """对单个 Chunk 调用大模型接口"""
        original_text = chunk.get("text", "")
        if not original_text.strip():
            return {"index": index, "action": "reject", "reason": "empty"}

        user_prompt = self.user_prompt_template.format(text=original_text)
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1, # 保持严谨，不引发幻觉
        }

        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.post(self.api_url, headers=headers, json=payload, timeout=self.timeout)
                response.raise_for_status()
                result = response.json()
                content = result["choices"][0]["message"]["content"].strip()
                
                # 判断是否触发配置的拒绝词
                if "[REJECT]" in content.upper():
                    return {"index": index, "action": "reject", "reason": "llm_rejected"}
                elif "[UNCERTAIN]" in content.upper():
                    return {"index": index, "action": "uncertain", "reason": "llm_uncertain", "text": original_text}
                else:
                    return {"index": index, "action": "accept", "text": content}
                    
            except Exception as e:
                logger.warning(f"[Chunk {index}] LLM Call failed locally (attempt {attempt}): {e}")
                sleep_time = min(2 ** attempt, 8) # Max sleep 8 seconds to avoid ThreadPool blockage
                time.sleep(sleep_time)

        # 全重试失败，求稳保留原文本
        logger.error(f"[Chunk {index}] Exhausted all retries. Retaining original text.")
        return {"index": index, "action": "accept", "text": original_text}

    def process(self, context: Context) -> Context:
        if not self.api_key:
            context.mark_invalid("LLMChunkReviewerProcessor requires 'DEEPSEEK_API_KEY' environment variable or 'api_key' in config.")
            return context

        chunks = context.metadata.get("chunks", [])
        if not chunks:
            logger.warning("No chunks found in context.metadata. Skipping LLM review.")
            return context

        logger.info(f"🤖 Starting Concurrent LLM Review for {len(chunks)} chunks (Workers: {self.max_workers})...")
        start_time = time.time()
        
        reviewed_chunks = []
        rejected_count = 0
        
        # 使用多线程对所有 chunk 并发发起审核请求
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_chunk = {
                executor.submit(self._review_single_chunk, chunk, idx): (idx, chunk)
                for idx, chunk in enumerate(chunks)
            }
            
            # 收集结果，还原顺序（因为 as_completed 会打乱顺序）
            results_map = {}
            for future in as_completed(future_to_chunk):
                idx, orig_chunk = future_to_chunk[future]
                try:
                    res = future.result()
                    results_map[res["index"]] = (res, orig_chunk)
                except Exception as exc:
                    logger.error(f"Chunk {idx} generated an unexpected exception: {exc}")
                    results_map[idx] = ({"action": "accept", "text": orig_chunk.get("text")}, orig_chunk)

        # 按原索引顺序重组新的 chunks 数组
        uncertain_count = 0
        for idx in range(len(chunks)):
            if idx not in results_map:
                continue
                
            res, orig_chunk = results_map[idx]
            if res["action"] == "reject":
                rejected_count += 1
            elif res["action"] == "uncertain":
                orig_chunk["is_uncertain"] = True
                orig_chunk["llm_reviewed"] = True
                uncertain_count += 1
                reviewed_chunks.append(orig_chunk)
            else:
                # 覆盖原来的 OCR 文本
                orig_chunk["text"] = res["text"]
                orig_chunk["is_uncertain"] = False
                orig_chunk["llm_reviewed"] = True
                reviewed_chunks.append(orig_chunk)

        duration = time.time() - start_time
        logger.info(f"✅ LLM Review Complete in {duration:.2f}s! Kept: {len(reviewed_chunks)}, Rejected: {rejected_count}, Uncertain: {uncertain_count}.")
        
        # 将提纯后的 chunks 复写回上下文
        context.metadata["chunks"] = reviewed_chunks
        return context
