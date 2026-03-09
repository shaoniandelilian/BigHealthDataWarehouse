# -*- coding: utf-8 -*-
import re
import html
import logging
from typing import Dict, Any

from core.context import Context
from core.registry import ProcessorRegistry
from processors.base import BaseProcessor

logger = logging.getLogger("MarkdownCleanerProcessor")

# =========================================================
# Part 1: 图片 & HTML 表格删除
# =========================================================
INLINE_IMG = re.compile(r'!\[[^\]]*\]\(\s*[^)]+?\s*\)', flags=re.IGNORECASE)
REF_IMG = re.compile(r'!\[[^\]]*\]\s*\[[^\]]*\]', flags=re.IGNORECASE)
HTML_IMG = re.compile(r'<img\b[^>]*?>', flags=re.IGNORECASE)
HTML_TABLE = re.compile(
    r'<table\b[^>]*?>.*?</table>',
    flags=re.IGNORECASE | re.DOTALL
)

def strip_images_and_tables(text: str) -> str:
    text = INLINE_IMG.sub('', text)
    text = REF_IMG.sub('', text)
    text = HTML_IMG.sub('', text)
    text = HTML_TABLE.sub('', text)
    return text

# =========================================================
# Part 2: 图 / 表 引用与标题清洗
# =========================================================
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

def clean_inline_references(text: str) -> str:
    text = PAT_PAREN_REF.sub("", text)
    text = PAT_RU_REF.sub("", text)
    text = PAT_INLINE_FIG.sub("", text)
    return text

def remove_title_lines(text: str) -> str:
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
    text = remove_title_lines(text)
    text = clean_inline_references(text)
    return text

# =========================================================
# Part 3: Markdown 结构 & 行内规范化
# =========================================================
RE_MD_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*\S)\s*$")

def normalize_inline(text: str) -> str:
    text = html.unescape(text)

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

    unicode_math = {
        "∕": "/", "∖": "\\",
        "﹢": "+", "﹣": "-",
        "⁺": "+", "⁻": "-", "₊": "+", "₋": "-",
        "＜": "<", "＞": ">",
    }
    for k, v in unicode_math.items():
        text = text.replace(k, v)

    ocr_map = {
        "—": "-", "–": "-", "O": "0",
    }
    for k, v in ocr_map.items():
        text = text.replace(k, v)

    text = re.sub(r"[ \t]+", " ", text).strip()
    return text

def normalize_markdown(text: str) -> str:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out = []
    buf = []

    def flush():
        if buf:
            joined = " ".join(s.strip() for s in buf if s.strip())
            if joined:
                out.append(normalize_inline(joined))
            buf.clear()

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

# =========================================================
# Processor 包装
# =========================================================
@ProcessorRegistry.register("MarkdownCleanerProcessor")
class MarkdownCleanerProcessor(BaseProcessor):
    """
    负责将 OCR 出来的脏乱差 Markdown，通过严酷的正则过滤，
    剥离图片引用、表格标签、无关标题数字等噪音。
    """
    def process(self, context: Context) -> Context:
        raw_md = context.metadata.get('raw_markdown')
        if not raw_md:
            context.mark_invalid("MarkdownCleanerProcessor requires 'raw_markdown' in metadata. Was MinerUOCRProcessor running?")
            return context
            
        logger.info("🧹 Cleaning and normalizing markdown content...")
        
        # 依次过滤清洗
        text = strip_images_and_tables(raw_md)
        text = clean_references(text)
        text = normalize_markdown(text)
        
        # 将清洗完的结果缓存入 context 供下个阶段(分块)使用
        context.metadata['cleaned_markdown'] = text
        logger.info(f"✅ Cleaning complete. Cleaned md size: {len(text)} characters.")
        return context
