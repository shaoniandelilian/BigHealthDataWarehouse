#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
切块处理器
功能：
1. 清洗 Markdown 中的图片和表格引用
2. 混合分块策略：外部按标题结构切分，内部按语义切分
"""

import re
import html
import copy
import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Callable
from pathlib import Path

from core.context import Context
from processors.base import BaseProcessor
from core.registry import registry

logger = logging.getLogger(__name__)


# =========================================================
# Part 1：Markdown 清洗（图片、表格、引用清理）
# =========================================================

# 图片相关正则
INLINE_IMG = re.compile(r'!\[[^\]]*\]\(\s*[^)]+?\s*\)', flags=re.IGNORECASE)
REF_IMG = re.compile(r'!\[[^\]]*\]\s*\[[^\]]*\]', flags=re.IGNORECASE)
HTML_IMG = re.compile(r'<img\b[^>]*?>', flags=re.IGNORECASE)
HTML_TABLE = re.compile(
    r'<table\b[^>]*?>.*?</table>',
    flags=re.IGNORECASE | re.DOTALL
)

# 图/表引用正则
PAT_PAREN_REF = re.compile(
    r"\(\s*(图|表)\s*[\dA-Za-z]+(?:[-.,、]\s*[\dA-Za-z]+)*\s*\)",
    flags=re.IGNORECASE
)
PAT_RU_REF = re.compile(
    r"如(图|表)\s*\d+(?:[-.]\d+)*\s*所示",
    flags=re.IGNORECASE
)
PAT_INLINE_FIG = re.compile(
    r"(图|表)\s*\d+(?:[.\-]\d+)*[A-Za-z]?",
    flags=re.IGNORECASE
)
PAT_LINE_TITLE = re.compile(
    r""" ^
        \s*
        (图|表)
        \s*
        \d+(?:[.\-]\d+)*[A-Za-z]?
        (?!是)
        (?!.*。.*)
        (?!.*\b(因此|但是|然而|另外|此外)\b)
        .{1,800}
        $
    """,
    re.VERBOSE
)
PAT_CONTINUED_TABLE = re.compile(r"^\s*续表\s*$")

# 标题正则
RE_MD_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*\S)\s*$")
RE_MD_HEADING_LINE = re.compile(r"^\s{0,3}#{1,6}\s+.*$", flags=re.MULTILINE)

# 公式保护正则
MATH_PATTERN = re.compile(r"\$.*?\$", flags=re.DOTALL)


def strip_images_and_tables(text: str) -> str:
    """删除图片和HTML表格"""
    text = INLINE_IMG.sub('', text)
    text = REF_IMG.sub('', text)
    text = HTML_IMG.sub('', text)
    text = HTML_TABLE.sub('', text)
    return text


def clean_inline_references(text: str) -> str:
    """清洗行内图/表引用"""
    text = PAT_PAREN_REF.sub("", text)
    text = PAT_RU_REF.sub("", text)
    text = PAT_INLINE_FIG.sub("", text)
    return text


def remove_title_lines(text: str) -> str:
    """删除图/表标题行"""
    lines = text.splitlines()
    kept = []
    for line in lines:
        if PAT_LINE_TITLE.match(line):
            continue
        if PAT_CONTINUED_TABLE.match(line):
            continue
        kept.append(line)
    return "\n".join(kept)


def clean_references(text: str) -> str:
    """清洗所有图/表引用和标题"""
    text = remove_title_lines(text)
    text = clean_inline_references(text)
    return text


def normalize_inline(text: str) -> str:
    """行内文本规范化"""
    text = html.unescape(text)

    # LaTeX 符号替换
    latex_map = {
        r"\$\s*=\s*\$": "=",
        r"\$\s*-\s*\$": "-",
        r"\$\s*\+\s*\$": "+",
        r"\$\s*<\s*\$": "<",
        r"\$\s*>\s*\$": ">",
        r"\\times": "×",
        r"\\cdot": "·",
        r"\\pm": "±",
    }
    for p, r in latex_map.items():
        text = re.sub(p, r, text)

    # 全角转半角
    full2half = {
        "＋": "+", "－": "-", "＝": "=", "／": "/",
        "％": "%", "；": ";", "：": ":", "（": "(",
        "）": ")", "【": "[", "】": "]", "，": ",",
        "。": ".", "？": "?", "！": "!",
        "“": "\"", "”": "\"", "‘": "'", "’": "'",
        "、": ",",
    }
    for k, v in full2half.items():
        text = text.replace(k, v)

    # Unicode 数学符号
    unicode_math = {
        "∕": "/", "∖": "\\", "﹢": "+", "﹣": "-",
        "⁺": "+", "⁻": "-", "₊": "+", "₋": "-",
        "＜": "<", "＞": ">",
    }
    for k, v in unicode_math.items():
        text = text.replace(k, v)

    # OCR 常见错误
    ocr_map = {"—": "-", "–": "-"}
    for k, v in ocr_map.items():
        text = text.replace(k, v)

    text = re.sub(r"[ \t]+", " ", text).strip()
    return text


def normalize_markdown(text: str) -> str:
    """Markdown 结构规范化"""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    out = []
    buf = []

    def flush():
        nonlocal buf
        if buf:
            joined = " ".join(s.strip() for s in buf if s.strip())
            if joined:
                out.append(normalize_inline(joined))
            buf = []

    for line in lines:
        m = RE_MD_HEADING.match(line)
        if m:
            flush()
            out.append(f"{m.group(1)} {normalize_inline(m.group(2))}")
            continue

        if not line.strip():
            flush()
            continue

        buf.append(line)

    flush()
    return "\n".join(out) + "\n"


def clean_markdown_pipeline(text: str) -> str:
    """
    Markdown 清洗总 Pipeline
    1. 删除图片和表格
    2. 清洗图/表引用
    3. 规范化 Markdown
    """
    text = strip_images_and_tables(text)
    text = clean_references(text)
    text = normalize_markdown(text)
    return text


# =========================================================
# Part 2：公式保护工具
# =========================================================

def protect_math(text: str) -> Tuple[str, Dict[str, str]]:
    """
    保护数学公式，替换为占位符
    返回: (保护后的文本, 占位符到原始公式的映射)
    """
    math_map = {}
    counter = 0

    def repl(m):
        nonlocal counter
        key = f"__MATH_{counter}__"
        math_map[key] = m.group(0)
        counter += 1
        return key

    protected_text = MATH_PATTERN.sub(repl, text)
    return protected_text, math_map


def restore_math(text: str, math_map: Dict[str, str]) -> str:
    """还原数学公式"""
    for k, v in math_map.items():
        text = text.replace(k, v)
    return text


def normalize_latex_for_embedding(text: str) -> str:
    """
    将常见医学 LaTeX 表达转为自然语言
    """
    # CO₂ / O₂ 等
    text = re.sub(
        r"\$\\(?:mathsf|mathrm)\s*\{\s*([A-Za-z]+)\s*\}\s*_\s*\{\s*(\d+)\s*\}\s*\$",
        lambda m: f"{m.group(1)}{m.group(2)}",
        text
    )

    # 数值范围：3.89 \sim 6.11 mmol/L
    text = re.sub(
        r"\$\s*([\d\s\.]+)\s*\\sim\s*([\d\s\.]+)\s*\\mathrm\s*\{\s*mmol\s*/\s*L\s*\}\s*\$",
        lambda m: f"{m.group(1).replace(' ', '')}–{m.group(2).replace(' ', '')} mmol/L",
        text
    )

    # 单独的 mmol/L
    text = re.sub(
        r"\$\\mathrm\s*\{\s*mmol\s*/\s*L\s*\}\$",
        "mmol/L",
        text
    )

    # 清理多余空格
    text = re.sub(r"\s{2,}", " ", text)

    return text.strip()


# =========================================================
# Part 3：中文空格清理
# =========================================================

def remove_spaces_in_chinese_text(text: str) -> str:
    """
    删除中文语境中的多余空格
    """
    if not text:
        return text

    # 中文 + 空格 + 中文
    text = re.sub(
        r'([\u4e00-\u9fff])\s+([\u4e00-\u9fff])',
        r'\1\2',
        text
    )

    # 中文 + 空格 + 中英文标点
    text = re.sub(
        r'([\u4e00-\u9fff])\s+([，。；：！？,.;:!?）】》])',
        r'\1\2',
        text
    )

    # 中英文标点 + 空格 + 中文
    text = re.sub(
        r'([（【《,.;:!?])\s+([\u4e00-\u9fff])',
        r'\1\2',
        text
    )

    return text


def remove_markdown_headings(text: str) -> str:
    """删除 Markdown 标题行"""
    if not text:
        return text
    cleaned = RE_MD_HEADING_LINE.sub("", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


# =========================================================
# Part 4：结构切分器（按标题层级）
# =========================================================

@dataclass
class Chunk:
    """文本块数据结构"""
    content: str = ""
    metadata: dict = field(default_factory=dict)


class MarkdownHeaderTextSplitter:
    """
    Markdown 标题结构切分器
    按标题层级将文档切分为结构块
    """

    def __init__(
        self,
        headers_to_split_on: Optional[List[Tuple[str, str]]] = None,
        strip_headers: bool = True,
        chunk_size: Optional[int] = None,
    ):
        self.strip_headers = strip_headers
        self.chunk_size = chunk_size

        # 默认按 h1-h6 切分
        if headers_to_split_on is None:
            headers_to_split_on = [
                ("#", "h1"),
                ("##", "h2"),
                ("###", "h3"),
                ("####", "h4"),
                ("#####", "h5"),
                ("######", "h6"),
            ]

        # 按 # 数量降序排列，确保先匹配 ###### 再匹配 #
        self.headers_to_split_on = sorted(
            headers_to_split_on,
            key=lambda x: len(x[0]),
            reverse=True
        )

    def split_text(self, text: str, metadata: Optional[dict] = None) -> List[Chunk]:
        """
        按标题层级切分文本
        """
        base_metadata = metadata or {}
        lines = text.split("\n")

        lines_with_metadata: List[Dict] = []
        current_content: List[str] = []
        current_metadata: Dict[str, str] = {}
        header_stack: List[Dict] = []

        in_code_block = False
        opening_fence = ""

        for line in lines:
            stripped = line.strip()

            # 代码块处理
            is_code_fence = False
            if not in_code_block:
                if stripped.startswith("```") and stripped.count("```") == 1:
                    in_code_block = True
                    opening_fence = "```"
                    is_code_fence = True
                elif stripped.startswith("~~~") and stripped.count("~~~") == 1:
                    in_code_block = True
                    opening_fence = "~~~"
                    is_code_fence = True
            else:
                if opening_fence and stripped.startswith(opening_fence):
                    in_code_block = False
                    opening_fence = ""
                    is_code_fence = True

            if in_code_block or is_code_fence:
                current_content.append(line)
                continue

            # 标题检测
            found_header = False
            for sep, name in self.headers_to_split_on:
                if stripped.startswith(sep) and (
                    len(stripped) == len(sep) or stripped[len(sep)] == " "
                ):
                    found_header = True
                    level = sep.count("#")
                    header_data = stripped[len(sep):].strip()

                    # 保存当前内容
                    if current_content:
                        lines_with_metadata.append({
                            "content": "\n".join(current_content),
                            "metadata": current_metadata.copy(),
                        })
                        current_content = []

                    # 更新标题栈
                    while header_stack and header_stack[-1]["level"] >= level:
                        header_stack.pop()
                    header_stack.append({"level": level, "name": name, "data": header_data})
                    current_metadata = {h["name"]: h["data"] for h in header_stack}

                    # 是否保留标题行
                    if not self.strip_headers:
                        current_content.append(line)
                    break

            if not found_header:
                if stripped or current_content:
                    current_content.append(line)

        # 保存最后的内容
        if current_content:
            lines_with_metadata.append({
                "content": "\n".join(current_content),
                "metadata": current_metadata.copy(),
            })

        # 合并相同元数据的行
        return self._aggregate_lines_to_chunks(lines_with_metadata, base_metadata)

    def _aggregate_lines_to_chunks(
        self,
        lines: List[Dict],
        base_meta: dict
    ) -> List[Chunk]:
        """合并相同元数据的行"""
        aggregated: List[Dict] = []
        for line in lines:
            if not line["content"].strip():
                continue
            if aggregated and aggregated[-1]["metadata"] == line["metadata"]:
                aggregated[-1]["content"] += "\n" + line["content"]
            else:
                aggregated.append(copy.deepcopy(line))

        final_chunks: List[Chunk] = []
        for item in aggregated:
            meta = base_meta.copy()
            meta.update(item["metadata"])
            final_chunks.append(Chunk(content=item["content"], metadata=meta))

        return final_chunks


# =========================================================
# Part 5：语义切分器（简化版，基于句子边界）
# =========================================================

class SemanticChunker:
    """
    语义切分器（简化版）
    基于句子边界进行语义切分
    """

    def __init__(
        self,
        max_chunk_size: int = 384,
        min_chunk_size: int = 100,
        sentence_end_pattern: str = r"[。！？!?；;\n]",
    ):
        self.max_chunk_size = max_chunk_size
        self.min_chunk_size = min_chunk_size
        self.sentence_pattern = re.compile(sentence_end_pattern)

    def split_text(self, text: str) -> List[str]:
        """
        将文本按语义切分为多个块
        """
        if not text.strip():
            return []

        # 先按句子切分
        sentences = self._split_to_sentences(text)

        # 合并句子为语义块
        chunks = []
        current_chunk = []
        current_length = 0

        for sentence in sentences:
            sent_len = len(sentence)

            # 如果单句超过最大长度，需要强制切分
            if sent_len > self.max_chunk_size:
                if current_chunk:
                    chunks.append("".join(current_chunk))
                    current_chunk = []
                    current_length = 0

                # 强制切分长句
                sub_chunks = self._force_split(sentence)
                chunks.extend(sub_chunks)
                continue

            # 如果添加后超过最大长度，先保存当前块
            if current_length + sent_len > self.max_chunk_size and current_chunk:
                chunks.append("".join(current_chunk))
                current_chunk = [sentence]
                current_length = sent_len
            else:
                current_chunk.append(sentence)
                current_length += sent_len

            # 如果达到最小长度且遇到句子边界，可以结束当前块
            if current_length >= self.min_chunk_size:
                chunks.append("".join(current_chunk))
                current_chunk = []
                current_length = 0

        # 保存最后的内容
        if current_chunk:
            chunks.append("".join(current_chunk))

        return [c.strip() for c in chunks if c.strip()]

    def _split_to_sentences(self, text: str) -> List[str]:
        """按句子边界切分"""
        # 保留分隔符
        parts = self.sentence_pattern.split(text)
        separators = self.sentence_pattern.findall(text)

        sentences = []
        for i, part in enumerate(parts):
            if part.strip():
                if i < len(separators):
                    sentences.append(part + separators[i])
                else:
                    sentences.append(part)

        return sentences

    def _force_split(self, text: str) -> List[str]:
        """对超长文本强制切分"""
        chunks = []
        start = 0

        while start < len(text):
            end = start + self.max_chunk_size

            if end >= len(text):
                chunks.append(text[start:])
                break

            # 尝试在句子边界切分
            search_start = max(start, end - 50)
            search_text = text[search_start:end]
            matches = list(self.sentence_pattern.finditer(search_text))

            if matches:
                split_pos = search_start + matches[-1].end()
            else:
                split_pos = end

            chunks.append(text[start:split_pos])
            start = split_pos

        return chunks


# =========================================================
# Part 6：混合切分处理器
# =========================================================

class HybridChunkProcessor:
    """
    混合切分处理器
    1. 外部按标题结构切分
    2. 内部按语义切分
    3. 控制块大小在合理范围内
    4. 过滤长度小于阈值的块
    """

    def __init__(
        self,
        max_chunk_size: int = 384,
        min_chunk_size: int = 100,
        strip_headers: bool = True,
        min_output_length: int = 120,  # 最终输出块的最小长度，小于此值的块将被过滤（默认120）
    ):
        self.max_chunk_size = max_chunk_size
        self.min_chunk_size = min_chunk_size
        self.strip_headers = strip_headers
        self.min_output_length = min_output_length  # 最小输出长度限制

        # 初始化切分器
        self.struct_splitter = MarkdownHeaderTextSplitter(
            strip_headers=strip_headers
        )
        self.semantic_splitter = SemanticChunker(
            max_chunk_size=max_chunk_size,
            min_chunk_size=min_chunk_size
        )

    def process(
        self,
        markdown_text: str,
        source_file: str = "",
        job_id: str = "",
    ) -> List[Dict]:
        """
        处理 Markdown 文本，返回切块结果

        Args:
            markdown_text: 清洗后的 Markdown 文本
            source_file: 来源文件名
            job_id: 任务ID

        Returns:
            切块结果列表，每个块包含 content 和 metadata
        """
        if not markdown_text.strip():
            logger.warning(f"Empty markdown text for job {job_id}")
            return []

        # Step 1: 清洗 Markdown
        cleaned_text = clean_markdown_pipeline(markdown_text)

        if not cleaned_text.strip():
            logger.warning(f"Text became empty after cleaning for job {job_id}")
            return []

        # Step 2: 按标题结构切分
        base_meta = {
            "source_file": source_file,
            "job_id": job_id,
        }

        struct_chunks = self.struct_splitter.split_text(cleaned_text, metadata=base_meta)
        logger.info(f"Structurally split into {len(struct_chunks)} chunks for job {job_id}")

        # Step 3: 对每个结构块进行语义切分
        final_chunks = []
        chunk_id = 0

        for struct_idx, struct_chunk in enumerate(struct_chunks, 1):
            if not struct_chunk.content.strip():
                continue

            # 构建元数据
            struct_meta = dict(struct_chunk.metadata or {})
            struct_meta["structural_index"] = struct_idx
            struct_meta["header_path"] = self._build_header_path(struct_meta)

            # 公式保护
            protected_text, math_map = protect_math(struct_chunk.content)

            # 语义切分
            semantic_texts = self.semantic_splitter.split_text(protected_text)

            # 处理每个语义块
            for sem_idx, sem_text in enumerate(semantic_texts, 1):
                if not sem_text.strip():
                    continue

                # 还原公式
                restored_text = restore_math(sem_text, math_map)

                # 清理中文空格
                cleaned_sem = remove_spaces_in_chinese_text(restored_text)

                # 删除标题行（避免重复）
                final_text = remove_markdown_headings(cleaned_sem)

                # LaTeX 规范化
                final_text = normalize_latex_for_embedding(final_text)

                if not final_text.strip():
                    continue

                # 过滤长度小于 min_output_length 的块（0表示不过滤）
                if self.min_output_length > 0 and len(final_text) < self.min_output_length:
                    logger.debug(f"Skipping chunk with length {len(final_text)} (< {self.min_output_length})")
                    continue

                chunk_id += 1

                final_meta = dict(struct_meta)
                final_meta["semantic_index"] = sem_idx
                final_meta["chunk_id"] = f"{job_id}_chunk_{chunk_id}"
                final_meta["char_length"] = len(final_text)

                final_chunks.append({
                    "chunk_id": final_meta["chunk_id"],
                    "content": final_text,
                    "metadata": final_meta,
                })

        logger.info(f"Final chunks: {len(final_chunks)} for job {job_id} (filtered by min_length={self.min_output_length})")
        return final_chunks

    def _build_header_path(self, metadata: Dict[str, str]) -> str:
        """构建标题路径"""
        parts = []
        for key in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            v = metadata.get(key)
            if v:
                parts.append(v)
        return " / ".join(parts)


@registry.register("HybridAdvancedChunkerProcessor")
class HybridAdvancedChunkerProcessor(BaseProcessor):
    """
    高级混合切块器
    继承自老版知识库的强大清洗和数学公式保护能力。
    将上一层传递下来的 Markdown 文本进行结构+语义双重切分。
    """
    def __init__(
        self, 
        max_chunk_size: int = 384, 
        min_chunk_size: int = 100,
        strip_headers: bool = True,
        min_output_length: int = 120
    ):
        super().__init__()
        self.processor = HybridChunkProcessor(
            max_chunk_size=max_chunk_size,
            min_chunk_size=min_chunk_size,
            strip_headers=strip_headers,
            min_output_length=min_output_length
        )
        
    def process(self, context: Context) -> Context:
        # 获取输入
        if context.metadata.get("markdown_content"):
            markdown_text = context.metadata["markdown_content"]
        elif context.metadata.get("raw_markdown"):
            markdown_text = context.metadata["raw_markdown"]
        elif isinstance(context.raw_data, str):
            markdown_text = context.raw_data
        else:
            context.mark_invalid("No readable markdown string found in Context for HybridAdvancedChunkerProcessor.")
            return context
            
        source_file = context.metadata.get("input_pdf_path", "unknown.pdf")
        job_id = context.run_id or "local_job"
        
        # 执行老版本的超级清洗切块核心逻辑
        chunks_data = self.processor.process(
            markdown_text=markdown_text,
            source_file=source_file,
            job_id=job_id
        )
        
        if not chunks_data:
            context.mark_invalid("ChunkProcessor produced 0 chunks.")
            return context
            
        # 写回 Context 继续往下流转
        # 兼容当前流水线的 chunks 格式
        formatted_chunks = []
        for c in chunks_data:
            # 兼容老版 {"chunk_id": "", "content": "", "metadata": {}} 到新版的风格
            formatted_chunks.append({
                "chunk_id": c.get("chunk_id", ""),
                "text": c.get("content", ""),
                "metadata": c.get("metadata", {})
            })
            
        context.metadata["chunks"] = formatted_chunks
        context.metadata["total_chunks"] = len(formatted_chunks)
        logger.info(f"HybridAdvancedChunkerProcessor finished: generated {len(formatted_chunks)} chunks.")
        
        return context
