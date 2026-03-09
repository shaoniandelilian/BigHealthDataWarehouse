# -*- coding: utf-8 -*-
import os
import time
import requests
import uuid
import logging
from typing import Dict, Any

from core.context import Context
from core.registry import ProcessorRegistry
from processors.base import BaseProcessor

logger = logging.getLogger("MinerUOCRProcessor")

@ProcessorRegistry.register("MinerUOCRProcessor")
class MinerUOCRProcessor(BaseProcessor):
    """
    PDF 提取器 — 支持多种后端：
    1. pymupdf4llm：纯 Python 提取方案，零模型下载，适合文本型 PDF。
    2. magic-pdf：深度学习方案，需要下载模型权重。
    3. 远程 API (MinerU)：通过 HTTP 调用远程服务器的 magic-pdf 引擎（推荐）。
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.output_dir = self.config.get("output_dir", "./data_process/result")
        self.backend = self.config.get("backend", "pymupdf4llm")
        self.mineru_host = self.config.get("mineru_host")
        self.mineru_port = self.config.get("mineru_port", 8000)
        
    def process(self, context: Context) -> Context:
        # 1. 获取输入 PDF 路径或 URL
        pdf_path = context.metadata.get("input_pdf_path")
        if not pdf_path and isinstance(context.raw_data, str):
            pdf_path = context.raw_data
        elif not pdf_path and isinstance(context.raw_data, dict):
            pdf_path = context.raw_data.get("pdf_path") or context.raw_data.get("file_path")
            
        if not pdf_path:
            context.mark_invalid("PDF file path or URL is missing in the payload")
            return context

        abs_output_dir = os.path.abspath(self.output_dir)
        os.makedirs(abs_output_dir, exist_ok=True)
            
        download_path = None
        # 1.5. 下载网络 URL（如果需要）
        if str(pdf_path).startswith("http://") or str(pdf_path).startswith("https://"):
            logger.info(f"🌐 Detected remote URL: {pdf_path}. Downloading...")
            try:
                response = requests.get(pdf_path, stream=True, timeout=60)
                response.raise_for_status()
                file_ext = ".md" if pdf_path.lower().endswith(".md") else ".pdf"
                tmp_filename = f"downloaded_{uuid.uuid4().hex[:8]}{file_ext}"
                download_path = os.path.join(abs_output_dir, tmp_filename)
                with open(download_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                pdf_path = download_path
            except Exception as e:
                context.mark_invalid(f"Failed to download remote file: {str(e)}")
                return context
                
        try:
            if not os.path.exists(pdf_path):
                context.mark_invalid(f"PDF file is missing or invalid: {pdf_path}")
                return context
                
            # 2. 如果输入就是 Markdown，直接读取
            if pdf_path.lower().endswith(".md") or pdf_path.lower().endswith(".markdown"):
                logger.info(f"Input is already a markdown file: {pdf_path}")
                with open(pdf_path, 'r', encoding='utf-8') as f:
                    context.metadata['raw_markdown'] = f.read()
                return context
    
            abs_pdf_path = os.path.abspath(pdf_path)
            logger.info(f"🚀 Starting PDF extraction: {os.path.basename(abs_pdf_path)} (backend={self.backend}, remote={bool(self.mineru_host)})")
            start_time = time.time()
            
            try:
                if self.mineru_host:
                    md_content = self._extract_remote_mineru(abs_pdf_path)
                elif self.backend == "pymupdf4llm":
                    md_content = self._extract_pymupdf4llm(abs_pdf_path)
                elif self.backend == "magic-pdf":
                    md_content = self._extract_magic_pdf(abs_pdf_path, abs_output_dir)
                else:
                    raise ValueError(f"Unknown backend: {self.backend}")
                
                # 备份结果
                base_name = os.path.splitext(os.path.basename(abs_pdf_path))[0]
                local_dir = os.path.join(abs_output_dir, base_name)
                os.makedirs(local_dir, exist_ok=True)
                local_md_path = os.path.join(local_dir, f"{base_name}.md")
                with open(local_md_path, "w", encoding="utf-8") as f:
                    f.write(md_content)
                    
                duration = time.time() - start_time
                logger.info(f"✅ PDF Extraction Complete! Cost: {duration:.2f}s")
                context.metadata['raw_markdown'] = md_content
                context.metadata['mineru_parse_duration'] = duration
                
            except Exception as e:
                context.mark_invalid(f"PDF Extraction Error: {str(e)}")
                logger.error("Error details:", exc_info=True)
                 
            return context
        finally:
            if download_path and os.path.exists(download_path):
                try:
                    os.remove(download_path)
                    logger.info(f"🗑️ Cleaned up temporary downloaded file: {download_path}")
                except Exception as cleanup_err:
                    logger.warning(f"Failed to clean up temporary file {download_path}: {cleanup_err}")
    
    def _extract_remote_mineru(self, pdf_path: str) -> str:
        """通过 HTTP 调用远程 MinerU 解析服务"""
        url = f"http://{self.mineru_host}:{self.mineru_port}/api/v1/parse"
        payload = {
            "pdf_path": pdf_path,
            "output_dir": self.output_dir,
            "parse_method": self.config.get("parse_method", "auto")
        }
        logger.info(f"📡 Calling remote MinerU at {url}...")
        response = requests.post(url, json=payload, timeout=600) # OCR 较慢，超时设长
        response.raise_for_status()
        data = response.json()
        if data.get("code") != 200:
            raise RuntimeError(f"Remote MinerU failed: {data.get('msg')}")
        
        # 远程服务会返回生成的 markdown 路径，由于是同一台机器或挂载，直接读取
        md_path = data["data"]["markdown_path"]
        with open(md_path, "r", encoding="utf-8") as f:
            return f.read()

    def _extract_pymupdf4llm(self, pdf_path: str) -> str:
        import pymupdf4llm
        return pymupdf4llm.to_markdown(pdf_path)
    
    def _extract_magic_pdf(self, pdf_path: str, output_dir: str) -> str:
        from magic_pdf.tools.common import do_parse
        base_name = os.path.splitext(os.path.basename(pdf_path))[0]
        parse_method = self.config.get("parse_method", "auto")
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        do_parse(output_dir=output_dir, pdf_file_name=base_name, pdf_bytes_or_dataset=pdf_bytes, model_list=[], parse_method=parse_method)
        local_md_path = os.path.join(output_dir, base_name, parse_method, f"{base_name}.md")
        if not os.path.exists(local_md_path):
            local_md_path = os.path.join(output_dir, base_name, f"{base_name}.md")
        with open(local_md_path, "r", encoding="utf-8") as f:
            return f.read()
