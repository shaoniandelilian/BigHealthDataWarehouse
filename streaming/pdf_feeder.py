# -*- coding: utf-8 -*-
"""
本地 PDF 文件夹批量发报器 (PDF Feeder)
专门用来巡检某个本地目录，把下面所有的 PDF 找出来，构造成 Context 包。
顺滑接入我们的 PdfOcrProcessor 这条完全不同的流水链路。
"""
import os
import yaml
from pathlib import Path
from tqdm import tqdm

from core.context import Context
from core.pipeline import Pipeline
from utils.logger import setup_logger

logger = setup_logger("PdfFeeder")

class PdfFeeder:
    def __init__(self, config_path: str = "configs/pipeline_pdf.yaml"):
        # 读取专门配置了 PDF OCR -> Chunker -> Bge -> Milvus 的链路
        logger.info(f"PdfFeeder loading config from {config_path}")
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        self.pipeline = Pipeline(cfg["pipeline_steps"])

    def feed_directory(self, folder_path: str):
        """扫描目录里的所有 PDF 下发"""
        target_dir = Path(folder_path)
        if not target_dir.exists() or not target_dir.is_dir():
            logger.error(f"Directory not found: {folder_path}")
            return
            
        pdf_files = list(target_dir.rglob("*.pdf"))
        if not pdf_files:
            logger.warning(f"No PDFs found in {folder_path}")
            return
            
        logger.info(f"Found {len(pdf_files)} PDFs in {folder_path}. Starting ingestion...")
        
        success = 0
        failed = 0
        
        for file in tqdm(pdf_files, desc="Batch OCR Ingestion"):
            # 【核心】：构建起始 Context。后续的 PdfOcrProcessor 检测到 file_path 以 .pdf 结尾
            # 就会自动拦截它并用大模型跑 OCR！
            ctx = Context(raw_data={
                "id": f"pdf-{file.name}",
                "file_path": str(file.absolute()),
                "data_type": "document"
            })
            
            try:
                final_ctx = self.pipeline.run(ctx)
                if final_ctx.is_valid:
                    success += 1
                else:
                    failed += 1
            except Exception as e:
                 logger.error(f"Feeder loop encountered unhandled exception: {e}")
                 failed += 1
                 
        logger.info(f"Done! PDF Success: {success}, Failed: {failed}")

if __name__ == "__main__":
    import sys
    config_file = "configs/pipeline_pdf.yaml"
    if len(sys.argv) > 1:
        config_file = sys.argv[1]
        
    feeder = PdfFeeder(config_path=config_file)
    print("PDF Feeder is ready to replace old run_dpsk_ocr_pdf.py scripts as input router.")
    # feeder.feed_directory("/data/wuteng/某一批科研论文/")
