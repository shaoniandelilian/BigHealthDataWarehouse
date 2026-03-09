# -*- coding: utf-8 -*-
import re
import copy
import logging
import threading
from typing import Dict, Any, List, Optional, Tuple, Callable

from core.context import Context
from core.registry import ProcessorRegistry
from processors.base import BaseProcessor

# 运行时可能需要安装 langchain 和 transformers, 由 requirements 保证
try:
    from transformers import AutoTokenizer
    from langchain_core.documents import Document
    from langchain_huggingface import HuggingFaceEmbeddings
    from langchain_experimental.text_splitter import SemanticChunker
except ImportError as e:
    logging.warning(f"Could not import heavy dependencies for SemanticChunker. Ensure langchain_* and transformers are installed: {e}")

logger = logging.getLogger("SemanticChunkerProcessor")

# =========================================================================
# (此处完全复用实时链路文档中的基础类：Chunk, MarkdownHeaderTextSplitter 等)
# 由于文件字数过大，将其核心拆分逻辑直接封装在 Processor 内或作为内部工具。
# =========================================================================

class Chunk:
    def __init__(self, content: str = "", metadata: dict = None):
        self.content = content
        self.metadata = metadata or {}

class MarkdownHeaderTextSplitter:
    # ... [简化的拆解：这里我们直接用 LangChain 内置或精简版。为了全量兼容原始脚本，我们贴入核心拆分器逻辑]
    def __init__(
            self,
            headers_to_split_on: List[Tuple[str, str]],
            strip_headers: bool = False,
            chunk_size: Optional[int] = None,
            is_separator_regex: bool = False,
    ):
        self.headers_to_split_on = sorted(headers_to_split_on, key=lambda x: len(x[0]), reverse=True)
        self.strip_headers = strip_headers
        self._chunk_size = chunk_size
        self._is_separator_regex = is_separator_regex

    def split_text(self, text: str, metadata: Optional[dict] = None) -> List[Chunk]:
        base_metadata = metadata or {}
        lines = text.split("\n")

        lines_with_metadata = []
        current_content = []
        current_metadata = {}
        header_stack = []

        in_code_block = False
        opening_fence = ""

        for line in lines:
            stripped = line.strip()
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

            found_header = False
            for sep, name in self.headers_to_split_on:
                if stripped.startswith(sep) and (len(stripped) == len(sep) or stripped[len(sep)] == " "):
                    found_header = True
                    level = sep.count("#")
                    header_data = stripped[len(sep):].strip()

                    if current_content:
                        lines_with_metadata.append({
                            "content": "\n".join(current_content),
                            "metadata": current_metadata.copy(),
                        })
                        current_content = []

                    while header_stack and header_stack[-1]["level"] >= level:
                        header_stack.pop()
                    header_stack.append({"level": level, "name": name, "data": header_data})
                    current_metadata = {h["name"]: h["data"] for h in header_stack}

                    if not self.strip_headers:
                        current_content.append(line)
                    break

            if not found_header:
                if stripped or current_content:
                    current_content.append(line)

        if current_content:
            lines_with_metadata.append({
                "content": "\n".join(current_content),
                "metadata": current_metadata.copy(),
            })

        # Base chunk compilation
        final_chunks: List[Chunk] = []
        for item in lines_with_metadata:
            meta = base_metadata.copy()
            meta.update(item["metadata"])
            final_chunks.append(Chunk(content=item["content"], metadata=meta))
            
        return final_chunks

# ====== 全局静态工具 ======
RE_MD_HEADING_LINE = re.compile(r"^\s{0,3}#{1,6}\s+.*$", flags=re.MULTILINE)
SENT_END_PATTERN = re.compile(r"[。！？!?；;\n]")
MATH_PATTERN = re.compile(r"\$.*?\$", flags=re.DOTALL)

def remove_markdown_headings(text: str) -> str:
    if not text: return text
    cleaned = RE_MD_HEADING_LINE.sub("", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()

def remove_spaces_in_chinese_text(text: str) -> str:
    if not text: return text
    text = re.sub(r'([\u4e00-\u9fff])\s+([\u4e00-\u9fff])', r'\1\2', text)
    text = re.sub(r'([\u4e00-\u9fff])\s+([，。；：！？,.;:!?）】》])', r'\1\2', text)
    text = re.sub(r'([（【《,.;:!?])\s+([\u4e00-\u9fff])', r'\1\2', text)
    return text
    
def protect_math(text: str):
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

def restore_math(text: str, math_map: dict) -> str:
    for k, v in math_map.items():
        text = text.replace(k, v)
    return text

def normalize_latex_for_embedding(text: str) -> str:
    text = re.sub(r"\$\\(?:mathsf|mathrm)\s*\{\s*([A-Za-z]+)\s*\}\s*_\s*\{\s*(\d+)\s*\}\s*\$", lambda m: f"{m.group(1)}{m.group(2)}", text)
    text = re.sub(r"\$\s*([\d\s\.]+)\s*\\sim\s*([\d\s\.]+)\s*\\mathrm\s*\{\s*mmol\s*/\s*L\s*\}\s*\$", lambda m: f"{m.group(1).replace(' ', '')}–{m.group(2).replace(' ', '')} mmol/L", text)
    text = re.sub(r"\$\\mathrm\s*\{\s*mmol\s*/\s*L\s*\}\$", "mmol/L", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()

def split_by_max_tokens_with_sentence_backoff(text: str, tokenizer, max_tokens: int = 384, search_window: int = 128) -> List[str]:
    if not text.strip(): return []
    chunks = []
    remaining = text.strip()

    while remaining:
        enc = tokenizer(remaining, return_offsets_mapping=True, add_special_tokens=False, truncation=False)
        input_ids = enc["input_ids"]
        offsets = enc["offset_mapping"]

        if len(input_ids) <= max_tokens:
            chunks.append(remaining)
            break

        cut_token_idx = max_tokens - 1
        cut_char_pos = offsets[cut_token_idx][1]
        search_start_char = max(0, offsets[max(0, cut_token_idx - search_window)][0])
        back_text = remaining[search_start_char:cut_char_pos]
        matches = list(SENT_END_PATTERN.finditer(back_text))

        if matches:
            split_char_pos = search_start_char + matches[-1].end()
        else:
            split_char_pos = cut_char_pos

        left = remaining[:split_char_pos].strip()
        right = remaining[split_char_pos:].strip()

        if left: chunks.append(left)
        remaining = right

    return chunks

def build_header_path(meta: Dict[str, str]) -> str:
    parts = []
    for key in ["h1", "h2", "h3", "h4", "h5", "h6"]:
        v = meta.get(key)
        if v:
            parts.append(v)
    return " / ".join(parts)


@ProcessorRegistry.register("SemanticChunkerProcessor")
class SemanticChunkerProcessor(BaseProcessor):
    """
    文档粉碎机：将通过清洗后的长文本，
    先基于 Markdown 结构，再结合挂载在本地的 KaLM Embedding 的语义连贯度进行视窗滑动拆分。
    
    输出：一个包含多个 chunk（自带 text与metadata）的数组挂靠在 context.metadata['chunks'] 上。
    """
    
    _embeddings_model = None
    _tokenizer = None
    _lock = threading.Lock()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.embedding_dir = self.config.get("embedding_dir", "")
        self.device = self.config.get("device", "cpu")
        self.normalize_embeddings = self.config.get("normalize_embeddings", True)
        self.max_tokens = self.config.get("max_tokens", 384)
        
        # 懒加载防爆存，避免应用刚跑起来就爆显存
        self._lazy_init_models()
        
    def _lazy_init_models(self):
        with SemanticChunkerProcessor._lock:
            if SemanticChunkerProcessor._embeddings_model is None and self.embedding_dir:
                logger.info(f"⏳ Loading Chunking Embedding Model into {self.device}: {self.embedding_dir}")
                SemanticChunkerProcessor._embeddings_model = HuggingFaceEmbeddings(
                    model_name=self.embedding_dir,
                    model_kwargs={"device": self.device},
                    encode_kwargs={"normalize_embeddings": self.normalize_embeddings},
                )
                SemanticChunkerProcessor._tokenizer = AutoTokenizer.from_pretrained(self.embedding_dir, use_fast=True)

    def process(self, context: Context) -> Context:
        cleaned_md = context.metadata.get('cleaned_markdown', '')
        if not cleaned_md:
            context.mark_invalid("No 'cleaned_markdown' found for chunking process.")
            return context

        logger.info("✂️ Running Structural + Semantic Chunking...")

        # 1. 初始化两大法器
        struct_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[
                ("#", "h1"), ("##", "h2"), ("###", "h3"), 
                ("####", "h4"), ("#####", "h5"), ("######", "h6")
            ],
            strip_headers=self.config.get("strip_headers", True),
            chunk_size=self.config.get("struct_chunk_size", 150),
            is_separator_regex=True
        )

        semantic_splitter_tool = SemanticChunker(
            SemanticChunkerProcessor._embeddings_model,
            sentence_split_regex=r"(?<=[。！？!?\.])\s*",
            breakpoint_threshold_type="standard_deviation", # standard deviation breakpoint chunking!
            breakpoint_threshold_amount=2,
        )

        # 2. Pipeline 执行核心
        result_chunks = []
        out_id = 0
        
        # 将原始数据元数据带入
        base_meta = {
            "source_file": context.metadata.get("input_pdf_path", "unknown"),
        }
        
        # 第一层：打散 Markdown 标题层级
        structural_chunks = struct_splitter.split_text(cleaned_md, metadata=base_meta)

        for struct_idx, ch in enumerate(structural_chunks, start=1):
            if not ch.content.strip():
                continue

            ch_meta = dict(ch.metadata or {})
            ch_meta["structural_index"] = struct_idx
            ch_meta["header_path"] = build_header_path(ch_meta)

            # 公式防分裂保护护罩开启！
            protected_text, math_map = protect_math(ch.content)
            
            # 喂给基于模型向量的深度感知切分器
            docs_in = [Document(page_content=protected_text, metadata=ch_meta)]
            
            try:
                docs_out = semantic_splitter_tool.split_documents(docs_in)
            except Exception as e:
                logger.error(f"⚠️ Semantic Splitter Failed (Fallback to full chunk): {e}")
                docs_out = [Document(page_content=protected_text, metadata=ch_meta)]

            semantic_idx = 0
            for d in docs_out:
                if not d.page_content.strip():
                    continue

                # 收尾后处理：空格处理 -> 护盾脱除 -> LaTeX友好化
                space_cleaned = remove_spaces_in_chinese_text(d.page_content)
                restored_text = restore_math(space_cleaned, math_map)
                cleaned_text = remove_markdown_headings(restored_text)
                semantic_text = normalize_latex_for_embedding(cleaned_text)

                # 最后防超载硬锁 Token (backoff 到上一个句号)
                safe_chunks = split_by_max_tokens_with_sentence_backoff(
                    semantic_text,
                    tokenizer=SemanticChunkerProcessor._tokenizer,
                    max_tokens=self.max_tokens,
                )

                for sub_idx, sub_text in enumerate(safe_chunks, start=1):
                    if not sub_text.strip():
                        continue
                    
                    semantic_idx += 1
                    out_id += 1

                    final_meta = dict(d.metadata or {})
                    final_meta["semantic_index"] = semantic_idx
                    final_meta["sub_index"] = sub_idx
                    # 给每个切块追加 type 字段，方便最后加载到 milvus 使用的 schema
                    final_meta["type"] = "document_ai_chunk" 

                    result_chunks.append({
                        "id": out_id,
                        "text": sub_text,
                        "metadata": final_meta
                    })

        # 3. 把切碎的兵分千路收回 Context
        context.metadata['chunks'] = result_chunks
        logger.info(f"✅ Chunking Complete. Generated {len(result_chunks)} segmented chunks.")
        
        return context
