# -*- coding: utf-8 -*-
import logging
from typing import List

from core.context import Context
from core.registry import registry
from processors.base import BaseProcessor

@registry.register("MarkdownChunker")
class MarkdownChunker(BaseProcessor):
    """
    负责将长文本（尤其是由 PdfOcrProcessor 解析出来的长 Markdown）进行滑窗截断分块。
    这是一个很特殊的节点，它会**裂变**：在这个算子之前的 Context 都是 1 对 1。
    在此算子内部，长文本会被切分成多个子片段数组，附加在 context.metadata["chunks"] 里。
    这样后面的 BgeEmbedder 就可以一次性拿到一个 List[str] 去打多个向量。
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.logger = logging.getLogger("MarkdownChunker")
        # 每个段落最多允许多少字符
        self.chunk_size = self.config.get("chunk_size", 512)
        # 滑窗重叠大小
        self.chunk_overlap = self.config.get("chunk_overlap", 50)
        
    def process(self, context: Context) -> Context:
        # 寻找之前流水线产生的所有可能的大段文字，包括大模型生成的回答、或者 PDF 提取出来的 MD
        text_to_chunk = context.metadata.get("full_markdown") or context.metadata.get("deepseek_raw_content")
        
        if not text_to_chunk:
             return context
             
        try:
             # 我们用一个非常朴素的标准切分算法来处理字符串，避免引入像 LangChain 那么重的包。
             chunks = self._naive_split(text_to_chunk, self.chunk_size, self.chunk_overlap)
             self.logger.info(f"🔪 Chunked text of len {len(text_to_chunk)} into {len(chunks)} fragments.")
             
             # 将分块后的数组挂载到 metadata 里
             context.metadata["chunks"] = chunks
             
        except Exception as e:
             context.mark_invalid(f"Chunking failed: {e}")
             
        return context
        
    def _naive_split(self, text: str, chunk_size: int, overlap: int) -> List[str]:
         """朴素的按定长带重叠截断的方法"""
         # 若本来就够短，直接返回
         if len(text) <= chunk_size:
             return [text.strip()]
             
         chunks = []
         start = 0
         while start < len(text):
             end = start + chunk_size
             chunk = text[start:end]
             
             # 简单的按结尾是不是刚好遇到换行或者句号，避免切碎一个词
             # 实际上，若追求更高质量，可以通过正则表达式按 \n\n 切分。这里做了极简安全版。
             chunks.append(chunk.strip())
             start = end - overlap
         return chunks
