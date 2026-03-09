#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多层大模型过滤模块
三层过滤架构：
1. 结构过滤 (DeepSeek) - 检查文本结构完整性
2. 语义过滤 (千问/Qwen) - 句子修复 + 语义完整性检查
3. 价值过滤 (Kimi) - 信息价值评估
"""

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import time
import threading
import os
from threading import Semaphore

from core.context import Context
from processors.base import BaseProcessor
from core.registry import registry

logger = logging.getLogger(__name__)

# API 速率限制器 - 限制每个API的并发请求数
class RateLimiter:
    """API 速率限制器"""
    def __init__(self, max_concurrent: int = 5, delay_between_requests: float = 0.1):
        self.semaphore = Semaphore(max_concurrent)
        self.delay = delay_between_requests
        self.last_request_time = 0
        self.lock = threading.Lock()

    def acquire(self):
        """获取执行许可"""
        self.semaphore.acquire()
        # 确保请求之间有最小间隔
        with self.lock:
            now = time.time()
            elapsed = now - self.last_request_time
            if elapsed < self.delay:
                time.sleep(self.delay - elapsed)
            self.last_request_time = time.time()

    def release(self):
        """释放执行许可"""
        self.semaphore.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False


class FilterStatus(Enum):
    """过滤状态"""
    PASS = "pass"           # 通过
    REJECT = "reject"       # 拒绝
    NEED_REPAIR = "repair"  # 需要修复


@dataclass
class FilterResult:
    """单个过滤器的结果"""
    status: FilterStatus
    score: float  # 0-1
    reason: str = ""
    repaired_text: Optional[str] = None  # 修复后的文本（如果有）
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMFilterOutput:
    """LLM 过滤最终输出"""
    chunk_id: str
    original_content: str
    final_content: str
    passed: bool
    filter_results: Dict[str, FilterResult]  # 各层过滤结果
    total_score: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseLLMClient(ABC):
    """大模型客户端基类"""
    # 类级别的速率限制器，限制每个API的并发数
    _rate_limiters: Dict[str, RateLimiter] = {}
    _lock = threading.Lock()

    def __init__(self, api_key: str, model: str, base_url: Optional[str] = None, max_concurrent: int = 5):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.logger = logging.getLogger(self.__class__.__name__)
        self.max_concurrent = max_concurrent

        # 为每个API端点创建独立的速率限制器
        rate_limiter_key = f"{self.__class__.__name__}_{base_url}"
        with self._lock:
            if rate_limiter_key not in self._rate_limiters:
                self._rate_limiters[rate_limiter_key] = RateLimiter(
                    max_concurrent=max_concurrent,
                    delay_between_requests=0.05  # 50ms 间隔
                )
            self.rate_limiter = self._rate_limiters[rate_limiter_key]

    @abstractmethod
    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.3, max_retries: int = 3) -> str:
        """发送聊天请求，返回文本响应"""
        pass

    def _handle_retry(self, func: Callable, max_retries: int = 3, delay: float = 1.0):
        """带重试的执行"""
        for attempt in range(max_retries):
            try:
                return func()
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                self.logger.warning(f"Attempt {attempt + 1} failed: {e}, retrying...")
                time.sleep(delay * (2 ** attempt))  # 指数退避
        return None


class DeepSeekClient(BaseLLMClient):
    """DeepSeek API 客户端"""

    DEFAULT_MODEL = "deepseek-chat"

    def __init__(self, api_key: str, model: str = None, max_concurrent: int = 100):
        model = model or self.DEFAULT_MODEL
        super().__init__(api_key, model, "https://api.deepseek.com", max_concurrent)

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.3, max_retries: int = 3) -> str:
        def _call():
            with self.rate_limiter:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature
                }
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=60
                )
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"]

        return self._handle_retry(_call, max_retries)


class QwenClient(BaseLLMClient):
    """阿里云千问 API 客户端"""

    DEFAULT_MODEL = "qwen-plus"

    def __init__(self, api_key: str, model: str = None, max_concurrent: int = 100):
        model = model or self.DEFAULT_MODEL
        super().__init__(api_key, model, "https://dashscope.aliyuncs.com", max_concurrent)

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.3, max_retries: int = 3) -> str:
        def _call():
            with self.rate_limiter:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature
                }
                response = requests.post(
                    f"{self.base_url}/compatible-mode/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=120
                )
                response.raise_for_status()
                result = response.json()
                return result["choices"][0]["message"]["content"]

        return self._handle_retry(_call, max_retries)


class KimiClient(BaseLLMClient):
    """Kimi (Moonshot) API 客户端"""

    DEFAULT_MODEL = "moonshot-v1-32k"

    def __init__(self, api_key: str, model: str = None, max_concurrent: int = 100):
        model = model or self.DEFAULT_MODEL
        super().__init__(api_key, model, "https://api.moonshot.cn", max_concurrent)

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.3, max_retries: int = 3) -> str:
        def _call():
            with self.rate_limiter:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature
                }
                response = requests.post(
                    f"{self.base_url}/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=120
                )
                response.raise_for_status()
                result = response.json()
                if "choices" in result and len(result["choices"]) > 0:
                    return result["choices"][0]["message"]["content"]
                else:
                    raise ValueError(f"Unexpected response format: {result}")

        return self._handle_retry(_call, max_retries)


class BaseFilter(ABC):
    """过滤器基类"""

    def __init__(self, llm_client: BaseLLMClient, name: str):
        self.llm_client = llm_client
        self.name = name
        self.logger = logging.getLogger(f"{self.__class__.__name__}[{name}]")

    @abstractmethod
    def filter(self, content: str, metadata: Dict[str, Any] = None) -> FilterResult:
        """执行过滤，返回结果"""
        pass

    def _parse_json_response(self, response: str) -> Dict:
        """解析 JSON 响应，处理转义问题"""
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # 清理响应中的非法转义序列
        cleaned = response
        cleaned = cleaned.replace('\\d', 'd')
        cleaned = cleaned.replace('\\n', '\n')
        cleaned = cleaned.replace('\\t', '\t')
        cleaned = cleaned.replace('\\r', '')

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # 尝试从代码块中提取
        pattern = r'```(?:json)?\s*(.*?)\s*```'
        matches = re.findall(pattern, cleaned, re.DOTALL)
        if matches:
            try:
                return json.loads(matches[0])
            except json.JSONDecodeError:
                pass

        # 尝试提取 {} 包裹的内容
        pattern = r'\{[\s\S]*?\}'
        matches = re.findall(pattern, cleaned, re.DOTALL)
        if matches:
            for match in matches:
                try:
                    return json.loads(match)
                except json.JSONDecodeError:
                    continue

        # 如果都失败了，返回默认结果
        self.logger.warning(f"Cannot parse JSON, using default. Response preview: {response[:200]}")
        return {
            "status": "pass",
            "score": 0.7,
            "reason": "JSON parse error, defaulting to pass"
        }


class StructureFilter(BaseFilter):
    """结构完整性过滤器 (DeepSeek)"""

    SYSTEM_PROMPT = """你是大健康领域的文本结构清洗专家，负责识别并标记需要删除的非内容元素。

【严格删除 - 直接标记 reject】

1. 图表标题
   - "表7-1 水钠代谢紊乱的分类"
   - "图 11-25 紫细菌光合膜结构"

2. 纯目录索引（只有章节标题+页码）
   - "生命的物质基础/025第一节蛋白质的组成/026"
   - "第一节能量单位/018 第二节能量来源/018"

3. CIP数据 / 出版信息
   - "中国版本图书馆CIP数据核字(2016)第028604号"
   - "责任编辑:丁嘉凌 封面设计:林少娟"

4. 索引引用标记
   - "(本章第五节)", "见本章第二节", "见本篇4"

5. 品牌产品名
   - "阿莫西林分散片", "脑安滴丸", "尼莫地平"

【保留 - 有价值的内容】
- 《黄帝内经》等经典原文引用
- 中国居民膳食指南等权威建议
- 营养学定义、原理阐述
- 即使无具体数据，但有知识价值的定性描述

请以 JSON 格式返回：
{
    "status": "pass" | "reject",
    "score": 0.0-1.0,
    "reason": "说明原因",
    "content_type": "content|table_caption|index|metadata|brand"
}

评分：
- 0.8-1.0: pass，有价值内容
- 0.5-0.8: pass，内容一般但有保留价值
- 0.0-0.5: reject，纯目录/CIP/品牌等垃圾内容"""

    def filter(self, content: str, metadata: Dict[str, Any] = None) -> FilterResult:
        metadata = metadata or {}
        header_path = metadata.get("header_path", "")

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": f"标题路径: {header_path}\n\n文本内容:\n{content}\n\n判断是否需要删除。"}
        ]

        try:
            response = self.llm_client.chat(messages, temperature=0.3)
            result = self._parse_json_response(response)

            status = FilterStatus(result.get("status", "pass"))
            score = float(result.get("score", 0.5))

            return FilterResult(
                status=status,
                score=score,
                reason=result.get("reason", ""),
                metadata={
                    "content_type": result.get("content_type", "content")
                }
            )
        except Exception as e:
            self.logger.error(f"Structure filter failed: {e}")
            return FilterResult(
                status=FilterStatus.PASS,
                score=0.8,
                reason=f"Filter error: {str(e)}"
            )


class SemanticFilter(BaseFilter):
    """语义完整性过滤器 (千问/Qwen)"""

    SYSTEM_PROMPT = """你是大健康领域的语义分析和文本修复专家。

【必须删除】
1. 只有名词/缩写列表，无完整句子
   - "Glc:葡萄糖;Gal:半乳糖"
   - "人体"、"(田余祥)"

2. 品牌产品相关内容
   - "阿莫西林分散片执行..."
   - "脑安滴丸联用尼莫地平"

3. 非学术引用（除期刊名外）
   - 书名、卷数、页码："《医学入门》卷三"

【修复任务 - 重点】

4. 修复第一个主语缺失
   - 问题："它含挥发油，油中主要含..."
   - 修复：根据标题推断，如标题"桂花"→"桂花含挥发油"

5. 指代明确化
   - "它含有丰富的蛋白质" → 具体食物名
   - "该物质可以抗氧化" → 具体物质名
   - "这种维生素" → "维生素C"等

【保留提示】
- 保留《黄帝内经》"五谷为养，五果为助"等经典
- 保留膳食指南原则性建议（即使定性无数据）
- 保留营养学定义和原理

请以 JSON 格式返回：
{
    "status": "pass" | "reject" | "repair",
    "score": 0.0-1.0,
    "reason": "原因说明",
    "repaired_text": "修复后的文本（如有）",
    "should_delete": true/false
}

评分：
- 0.8-1.0: pass，语义完整清晰
- 0.5-0.8: repair，有小问题但已修复
- 0.0-0.5: reject，纯列表/品牌/引用无法修复"""

    def filter(self, content: str, metadata: Dict[str, Any] = None) -> FilterResult:
        metadata = metadata or {}
        header_path = metadata.get("header_path", "")

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": f"标题路径: {header_path}\n\n文本内容:\n{content}\n\n检查语义完整性。"}
        ]

        try:
            response = self.llm_client.chat(messages, temperature=0.4)
            result = self._parse_json_response(response)

            status = FilterStatus(result.get("status", "pass"))
            score = float(result.get("score", 0.5))

            if result.get("should_delete") and status != FilterStatus.REJECT:
                status = FilterStatus.REJECT
                score = min(score, 0.4)

            repaired_text = result.get("repaired_text")
            if status == FilterStatus.NEED_REPAIR and not repaired_text:
                repaired_text = content

            return FilterResult(
                status=status,
                score=score,
                reason=result.get("reason", ""),
                repaired_text=repaired_text if status == FilterStatus.NEED_REPAIR else None,
                metadata={}
            )
        except Exception as e:
            self.logger.error(f"Semantic filter failed: {e}")
            return FilterResult(
                status=FilterStatus.PASS,
                score=0.8,
                reason=f"Filter error: {str(e)}"
            )


class ValueFilter(BaseFilter):
    """信息价值过滤器 (Kimi)"""

    SYSTEM_PROMPT = """你是大健康领域的信息价值评估专家。

【最后防线 - 严格删除】
1. 残留品牌/产品
   - 药品名、商品名

2. 残留非学术引用
   - 书名卷数页码

3. 纯图表标题残留
   - "表X-X"、"图X-X"

【价值评估维度】
4. 营养知识价值
   - 高：具体数据 "牛奶每100ml含钙120mg"
   - 中：定性描述但有知识价值 "五谷为养，五果为助"
   - 低：纯常识 "要多吃蔬菜"

5. 医学指导价值
   - 高：可操作指导 "高血压患者每日钠摄入应控制在2000mg以下"
   - 中：原则性建议 "合理膳食，均衡营养"
   - 低：泛泛而谈 "要注意健康"

【特殊保留】
即使简短，以下情况保留：
- 经典理论引用（黄帝内经、膳食指南）
- 营养定义/原理阐述
- 中医食疗原则

请以 JSON 格式返回：
{
    "status": "pass" | "reject",
    "score": 0.0-1.0,
    "reason": "评估原因",
    "value_level": "high" | "medium" | "low"
}

评分：
- 0.7-1.0: pass，有价值内容（含经典引用、原则建议）
- 0.4-0.7: pass，中等价值
- 0.0-0.4: reject，品牌/引用/无价值内容"""

    def filter(self, content: str, metadata: Dict[str, Any] = None) -> FilterResult:
        metadata = metadata or {}
        header_path = metadata.get("header_path", "")

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": f"标题路径: {header_path}\n\n文本内容:\n{content}\n\n评估信息价值。"}
        ]

        try:
            response = self.llm_client.chat(messages, temperature=0.3)
            result = self._parse_json_response(response)

            status = FilterStatus(result.get("status", "pass"))
            score = float(result.get("score", 0.5))

            return FilterResult(
                status=status,
                score=score,
                reason=result.get("reason", ""),
                metadata={
                    "value_level": result.get("value_level", "medium")
                }
            )
        except Exception as e:
            self.logger.error(f"Value filter failed: {e}")
            return FilterResult(
                status=FilterStatus.PASS,
                score=0.8,
                reason=f"Filter error: {str(e)}"
            )


class LLMFilterPipeline:
    """LLM 多层过滤 Pipeline"""

    def __init__(
        self,
        deepseek_api_key: Optional[str] = None,
        qwen_api_key: Optional[str] = None,
        kimi_api_key: Optional[str] = None,
        deepseek_model: Optional[str] = None,
        qwen_model: Optional[str] = None,
        kimi_model: Optional[str] = None,
        enable_structure: bool = True,
        enable_semantic: bool = True,
        enable_value: bool = True,
        min_total_score: float = 0.5  # 降低阈值到 0.5
    ):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.min_total_score = min_total_score

        # 初始化过滤器
        self.filters: List[BaseFilter] = []

        if enable_structure and deepseek_api_key:
            deepseek_client = DeepSeekClient(deepseek_api_key, model=deepseek_model)
            self.filters.append(StructureFilter(deepseek_client, "structure"))
            self.logger.info("Structure filter (DeepSeek) enabled")

        if enable_semantic and qwen_api_key:
            qwen_client = QwenClient(qwen_api_key, model=qwen_model)
            self.filters.append(SemanticFilter(qwen_client, "semantic"))
            self.logger.info("Semantic filter (Qwen) enabled")

        if enable_value and kimi_api_key:
            kimi_client = KimiClient(kimi_api_key, model=kimi_model)
            self.filters.append(ValueFilter(kimi_client, "value"))
            self.logger.info("Value filter (Kimi) enabled")

        if not self.filters:
            self.logger.warning("No LLM filters enabled!")

    def process_chunk(self, chunk: Dict[str, Any]) -> LLMFilterOutput:
        """处理单个 chunk"""
        chunk_id = chunk.get("chunk_id", "unknown")
        content = chunk.get("content", "")
        metadata = chunk.get("metadata", {})

        self.logger.debug(f"Processing chunk {chunk_id}")

        filter_results = {}
        current_content = content
        scores = []
        weights = {"structure": 0.3, "semantic": 0.4, "value": 0.3}

        # 顺序执行各层过滤
        for filter_obj in self.filters:
            result = filter_obj.filter(current_content, metadata)
            filter_results[filter_obj.name] = result
            scores.append(result.score * weights.get(filter_obj.name, 0.33))

            # 如果被拒绝，直接返回
            if result.status == FilterStatus.REJECT:
                self.logger.debug(f"Chunk {chunk_id} rejected by {filter_obj.name}")
                current_total = sum(scores)
                return LLMFilterOutput(
                    chunk_id=chunk_id,
                    original_content=content,
                    final_content=current_content,
                    passed=False,
                    filter_results=filter_results,
                    total_score=current_total,
                    metadata={"rejected_at": filter_obj.name}
                )

            # 如果有修复文本，更新当前内容
            if result.status == FilterStatus.NEED_REPAIR and result.repaired_text:
                current_content = result.repaired_text
                self.logger.debug(f"Chunk {chunk_id} repaired by {filter_obj.name}")

        # 最终决策（加权总分）
        total_score = sum(scores)
        passed = total_score >= self.min_total_score

        return LLMFilterOutput(
            chunk_id=chunk_id,
            original_content=content,
            final_content=current_content,
            passed=passed,
            filter_results=filter_results,
            total_score=total_score,
            metadata={
                "original_length": len(content),
                "final_length": len(current_content),
                "was_repaired": current_content != content
            }
        )

    def process_chunks(self, chunks: List[Dict[str, Any]], max_workers: int = 100) -> List[LLMFilterOutput]:
        """并行批量处理 chunks"""
        if not self.filters:
            raise ValueError("No API keys/filters configured for LLM funnel pipeline.")
            
        results = []
        total = len(chunks)

        self.logger.info(f"Processing {total} chunks with {max_workers} workers")
        print(f"开始处理 {total} 个 chunks，并发数: {max_workers}")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_chunk = {
                executor.submit(self.process_chunk, chunk): chunk
                for chunk in chunks
            }

            completed = 0
            passed_count = 0
            rejected_count = 0
            for future in as_completed(future_to_chunk):
                chunk = future_to_chunk[future]
                try:
                    result = future.result()
                    results.append(result)
                    completed += 1
                    if result.passed:
                        passed_count += 1
                    else:
                        rejected_count += 1
                    if completed % 20 == 0 or completed == total:
                        print(f"进度: {completed}/{total} ({completed/total*100:.1f}%) | 通过: {passed_count} | 拒绝: {rejected_count}")
                except Exception as e:
                    self.logger.error(f"Error processing chunk {chunk.get('chunk_id', 'unknown')}: {e}")
                    # 按照用户要求：“该失败就失败，不假装通过”
                    raise RuntimeError(f"LLM API failure on chunk {chunk.get('chunk_id', 'unknown')}: {e}")

        self.logger.info(f"Completed processing {len(results)} chunks")
        return results


@registry.register("MultiLLMFilterProcessor")
class MultiLLMFilterProcessor(BaseProcessor):
    """
    多重 LLM 漏斗过滤网
    集成旧版的结构、语义、价值三层过滤能力。
    将上一层切出的 chunks 发送给大模型进行评分和修复。
    低分块截留，高分块/修复块放行。
    """
    def __init__(
        self,
        deepseek_api_key: Optional[str] = None,
        qwen_api_key: Optional[str] = None,
        kimi_api_key: Optional[str] = None,
        deepseek_model: Optional[str] = None,
        qwen_model: Optional[str] = None,
        kimi_model: Optional[str] = None,
        enable_structure: bool = True,
        enable_semantic: bool = True,
        enable_value: bool = True,
        min_total_score: float = 0.5,
        max_workers: int = 20
    ):
        super().__init__()
        self.max_workers = max_workers
        
        # 优先读取 yaml 配置传入的 key，否则降级使用环境变量
        ds_key = deepseek_api_key or os.getenv("DEEPSEEK_API_KEY")
        qw_key = qwen_api_key or os.getenv("QWEN_API_KEY")
        km_key = kimi_api_key or os.getenv("KIMI_API_KEY")
        
        self.filter_pipeline = LLMFilterPipeline(
            deepseek_api_key=ds_key,
            qwen_api_key=qw_key,
            kimi_api_key=km_key,
            deepseek_model=deepseek_model,
            qwen_model=qwen_model,
            kimi_model=kimi_model,
            enable_structure=enable_structure and bool(ds_key),
            enable_semantic=enable_semantic and bool(qw_key),
            enable_value=enable_value and bool(km_key),
            min_total_score=min_total_score
        )
        
    def process(self, context: Context) -> Context:
        if not self.filter_pipeline.filters:
            context.mark_invalid("Missing API keys for MultiLLMFilterProcessor. No models configured.")
            return context

        chunks = context.metadata.get("chunks", [])
        if not chunks:
            logger.warning("No chunks to filter in MultiLLMFilterProcessor.")
            return context
            
        # 兼容旧版的 process_chunks 格式要求
        legacy_input_chunks = []
        for c in chunks:
            legacy_input_chunks.append({
                "chunk_id": c.get("chunk_id", ""),
                "content": c.get("text", ""),
                "metadata": c.get("metadata", {})
            })
            
        # 开始并行过滤评估与修复
        logger.info(f"Filtering {len(legacy_input_chunks)} chunks via Multi-LLM funnel...")
        results: List[LLMFilterOutput] = self.filter_pipeline.process_chunks(
            legacy_input_chunks, 
            max_workers=self.max_workers
        )
        
        filtered_chunks = []
        rejected_details = []
        
        for result in results:
            if result.passed:
                # 重新构装回新管线格式，并使用已被修复的 final_content
                filtered_chunks.append({
                    "chunk_id": result.chunk_id,
                    "text": result.final_content,
                    "metadata": {
                        **result.metadata,
                        "llm_filtered": True,
                        "llm_score": result.total_score
                    }
                })
            else:
                rejected_details.append({
                    "chunk_id": result.chunk_id,
                    "score": result.total_score,
                    "reason": {k: v.reason for k, v in result.filter_results.items()}
                })
                
        # 更新至 Context
        context.metadata["chunks"] = filtered_chunks
        context.metadata["total_chunks"] = len(filtered_chunks)
        context.metadata["rejected_chunks_count"] = len(rejected_details)
        context.metadata["rejected_details"] = rejected_details
        
        logger.info(f"MultiLLM filter complete: {len(filtered_chunks)} passed, {len(rejected_details)} rejected.")
        
        if not filtered_chunks:
            context.mark_invalid("All chunks were rejected by the Multi-LLM filter pipeline.")
            
        return context
