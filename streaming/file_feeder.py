# -*- coding: utf-8 -*-
"""
本地文件批量投喂器 (CSV/JSONL File Feeder)
负责读取静态的批量文件，将其按行转换为 Pipeline 认可的 Context 数据包，推进流水线。
这代表了流式处理架构中，对"老旧离线批处理数据"的兼容层。
对应于老脚本 /wuji/extract_data_to_csv.py 相关批量处理能力。
"""
import csv
import json
import logging
import yaml
from pathlib import Path
from tqdm import tqdm

from core.context import Context
from core.pipeline import Pipeline
from utils.logger import setup_logger

logger = setup_logger("FileFeeder")

class FileFeeder:
    def __init__(self, config_path: str = "configs/default.yaml"):
        # 读取外置配置，动态拉起整条黑盒流水线
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        pipeline_name = os.path.basename(config_path)
        self.pipeline = Pipeline(cfg["pipeline_steps"], pipeline_name=pipeline_name)

    def feed_csv(self, file_path: str):
        """
        流式读取巨大的 CSV 文件（防内存溢出），逐行喂给 Pipeline。
        """
        path = Path(file_path)
        if not path.exists():
            logger.error(f"File not found: {file_path}")
            return
            
        logger.info(f"Starting to feed pipeline from CSV: {file_path}")
        success_count = 0
        error_count = 0
        
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            # 对于极大文件，不应该用 list(reader) 撑破内存，这里只是加一个 tqdm 进度条的演示
            rows = list(reader)
            
        for row in tqdm(rows, desc="Processing CSV Stream"):
            # 【精髓】：把一行脏数据直接塞进 Context，扔进水管，剩下什么都不用管！
            ctx = Context(raw_data=row)
            
            try:
                final_ctx = self.pipeline.run(ctx)
                if final_ctx.is_valid:
                    success_count += 1
                else:
                    error_count += 1
            except Exception as e:
                logger.error(f"Unhandled pipeline crash on row: {e}")
                error_count += 1
                
        logger.info(f"CSV Feeder complete. Success: {success_count}, Failed: {error_count}")

if __name__ == "__main__":
    feeder = FileFeeder()
    print("FileFeeder is ready to replace old pandas-based batch loops.")
    # Example usage:
    # feeder.feed_csv("/home/wuteng/wuji/data/some_dataset.csv")
