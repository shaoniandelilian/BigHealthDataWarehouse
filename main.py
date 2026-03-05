#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ChemRAG-Flow 一站式命令行启动工具 (Unified Entrypoint)
通过这一个脚本，您可以：
1. 启动常驻后台的 API 服务集群
2. 触发一次性的本地 PDF 或 CSV 跑批清洗任务
3. 跑一边本地仿真测试
"""

import os
import argparse
import sys
import uvicorn
import logging
from typing import Optional

# 禁用相对路径可能引发的深坑
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.logger import setup_logger
logger = setup_logger("Main")

def start_api_server(config_path: str, host: str, port: int):
    """一站式启动 API Gateway"""
    logger.info(f"🚀 Starting API Webhook Server using config: {config_path}")
    # 注入全局环境变量，供 api_server.py 读取
    os.environ["PIPELINE_CONFIG"] = config_path
    
    # 强制在当前控制台启动 uvicorn
    # 注意这边的第一个参数是 "streaming.api_server:app"
    uvicorn.run("streaming.api_server:app", host=host, port=port, reload=False)

def start_pdf_batch(config_path: str, target_dir: str):
    """一站式启动 PDF 批处理发报机"""
    logger.info(f"📄 Starting local PDF batch ingestion on: {target_dir}")
    from streaming.pdf_feeder import PdfFeeder
    feeder = PdfFeeder(config_path=config_path)
    feeder.feed_directory(target_dir)

def start_csv_batch(config_path: str, target_file: str):
    """一站式启动 CSV/JSONL 批处理发报机"""
    logger.info(f"📊 Starting local CSV/JSON batch ingestion on: {target_file}")
    from streaming.file_feeder import FileFeeder
    feeder = FileFeeder()
    feeder.fallback_config = config_path # Hack 用于临时替换配置
    feeder.process_file(target_file)
    
def start_simulation(config_path: str):
    """跑核心管线的 Mock 测试流"""
    logger.info(f"🧪 Starting simulation dummy pipeline run using: {config_path}")
    import yaml
    from core.context import Context
    from core.pipeline import Pipeline
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load config {config_path}: {e}")
        return

    steps = cfg.get("pipeline_steps", [])
    pipeline = Pipeline(steps)
    
    # 构建兼容化学专线和 PDF 专线的通用死数据
    mock_dirty_data = {
        "id": "mock-001",
        "name": "Aspirin",
        "raw_smiles": "CC(=O)OC1=CC=CC=C1C(=O)O",
        "file_path": "dummy.pdf" # 让 pdf 处理器不会报错
    }
    
    logger.info("=" * 40)
    logger.info(f"Incoming Event: {mock_dirty_data}")
    logger.info("=" * 40)
    
    ctx = Context(raw_data=mock_dirty_data)
    ctx.metadata["raw_smiles"] = mock_dirty_data["raw_smiles"]
    
    try:
        final_ctx = pipeline.run(ctx)
        logger.info("=" * 40)
        if getattr(final_ctx, 'is_pending_review', False):
            logger.info("⏸️ Pipeline paused for human review! (Simulation Success)")
        elif final_ctx.is_valid:
            logger.info("✅ Pipeline processed successfully to the end!")
            logger.info(f"Extracted Metadata Keys: {list(final_ctx.metadata.keys())}")
        else:
            logger.warning(f"❌ Pipeline aborted. Errors: {final_ctx.errors}")
    except KeyboardInterrupt:
        logger.warning("Pipeline Simulation interrupted by user.")


def main():
    parser = argparse.ArgumentParser(description="ChemRAG-Flow 统一中控台 (Master CLI)")
    
    # 子命令结构
    subparsers = parser.add_subparsers(dest="command", help="选择并启动系统中的某个指定微服务")
    
    # ==========================================
    # 命令 1: serve (启动核心 Webhook)
    # ==========================================
    parser_serve = subparsers.add_parser("serve", help="启动 FastAPI 实时数据提交流水线后台与人工审核网关")
    parser_serve.add_argument("-c", "--config", default="configs/pipeline_chemicals.yaml", help="指定 YAML 配置文件路径")
    parser_serve.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser_serve.add_argument("--port", type=int, default=8000, help="监听端口 (默认 8000)")

    # ==========================================
    # 命令 2: batch_pdf (扫 PDF 目录入库)
    # ==========================================
    parser_pdf = subparsers.add_parser("batch_pdf", help="离线任务：批量将目标文件夹中的所有 PDF 抽取并入库")
    parser_pdf.add_argument("--dir", required=True, help="要扫描入库的本地绝对路径文件夹")
    parser_pdf.add_argument("-c", "--config", default="configs/pipeline_pdf.yaml", help="配置一定要选用附带 Ocr 算子的模版")

    # ==========================================
    # 命令 3: batch_csv (读表入库)
    # ==========================================
    parser_csv = subparsers.add_parser("batch_csv", help="离线任务：批量将旧版 CSV 生成文件按行灌入流水线")
    parser_csv.add_argument("--file", required=True, help="要清洗的目标 CSV 数据表绝对路径")
    parser_csv.add_argument("-c", "--config", default="configs/pipeline_chemicals.yaml", help="配置文件")

    # ==========================================
    # 命令 4: test (纯本地 Mock 运转测试)
    # ==========================================
    parser_test = subparsers.add_parser("test", help="测试环境能否不崩盘，执行一遍基础流")
    parser_test.add_argument("-c", "--config", default="configs/pipeline_chemicals.yaml", help="配置文件")

    args = parser.parse_args()

    # 路由选择分发
    if args.command == "serve":
        start_api_server(args.config, args.host, args.port)
    elif args.command == "batch_pdf":
        start_pdf_batch(args.config, args.dir)
    elif args.command == "batch_csv":
        start_csv_batch(args.config, args.file)
    elif args.command == "test":
        start_simulation(args.config)
    else:
        parser.print_help()
        print("\n\n请在末尾加上你需要的服务名。例如：")
        print("python main.py serve --config configs/pipeline_chemicals.yaml")
        sys.exit(1)

if __name__ == "__main__":
    main()
