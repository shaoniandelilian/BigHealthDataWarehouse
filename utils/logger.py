# -*- coding: utf-8 -*-
import logging
import sys
import os
from logging.handlers import RotatingFileHandler

def setup_logger(name: str = "ChemRAG") -> logging.Logger:
    """
    统一的日志配置组件。
    支持控制台输出，以及自动切割的本地文件记录。
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    if not logger.handlers:
        # 确保 logs 文件夹存在
        log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
        os.makedirs(log_dir, exist_ok=True)
        
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-7s | [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        
        # 1. 控制台输出 (Stdout)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        # 2. 全量业务日志 (自动滚动切割，单文件最多 10MB，保留 5 份)
        file_path = os.path.join(log_dir, "pipeline.log")
        file_handler = RotatingFileHandler(
            file_path, maxBytes=10*1024*1024, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        # 3. 错误与告警专属日志 (方便单独排查问题)
        error_file_path = os.path.join(log_dir, "errors.log")
        error_handler = RotatingFileHandler(
            error_file_path, maxBytes=10*1024*1024, backupCount=5, encoding="utf-8"
        )
        error_handler.setLevel(logging.WARNING)
        error_handler.setFormatter(formatter)
        logger.addHandler(error_handler)
        
    return logger

# 接管根节点日志
logging.basicConfig(level=logging.INFO)
