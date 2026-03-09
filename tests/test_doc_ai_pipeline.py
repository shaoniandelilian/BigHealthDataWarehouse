# -*- coding: utf-8 -*-
import os
import sys
import yaml
import logging

# 将根目录加到 sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.pipeline import Pipeline
from core.context import Context

# 为了触发装饰器注册，强制导入我们新写的处理器模块
import processors.extraction.mineru_extractor
import processors.transformation.markdown_cleaner
import processors.transformation.semantic_chunker
import processors.transformation.yuan_embedder
import processors.load.milvus_type_loader

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("TestDocAIPipeline")


def run_test():
    # 1. 挂载我们新写的配置文件
    config_path = os.path.join(os.path.dirname(__file__), "../configs/pipeline_doc_ai.yaml")
    if not os.path.exists(config_path):
        logger.error(f"Config file not found: {config_path}")
        return
        
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
        
    steps = config.get("pipeline_steps", [])
    if not steps:
        logger.error("No pipeline steps found in config!")
        return
        
    logger.info("🔧 Instantiating Pipeline...")
    pipeline = Pipeline(steps)
    
    # 获取测试所需 PDF 列表
    pdf_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../data/pdf"))
    try:
        pdf_files = [os.path.join(pdf_dir, f) for f in os.listdir(pdf_dir) if f.endswith(".pdf")]
    except FileNotFoundError:
        logger.error(f"PDF directory not found at {pdf_dir}")
        return
        
    if not pdf_files:
        logger.warning(f"No PDFs found in {pdf_dir}")
        return

    for pdf_path in pdf_files:
        logger.info(f"\n=========================================\n🚀 Starting Pipeline for: {os.path.basename(pdf_path)}\n=========================================")
        context = Context(raw_data=pdf_path)
        
        try:
            final_context = pipeline.run(context)
            
            logger.info(f"🎉 Pipeline Execution Finished for {os.path.basename(pdf_path)}")
            logger.info(f"Valid Data: {final_context.is_valid}")
            logger.info(f"Errors: {final_context.errors}")
            
            chunks = final_context.metadata.get("chunks", [])
            logger.info(f"Total Chunks Generated: {len(chunks)}")
            logger.info(f"Milvus Inserted Count: {final_context.metadata.get('milvus_inserted_count', 0)}")
            
            if final_context.is_valid and chunks:
                 logger.info(f"✅ SUCCESS: {os.path.basename(pdf_path)} flown through the pipeline seamlessly.")
            else:
                 logger.warning(f"⚠️ FAILED or Stopped early for {os.path.basename(pdf_path)}.")
        except Exception as e:
            logger.error(f"🔥 Uncaught Exception processing {pdf_path}: {e}", exc_info=True)

if __name__ == "__main__":
    run_test()
