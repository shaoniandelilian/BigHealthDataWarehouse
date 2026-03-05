# -*- coding: utf-8 -*-
import importlib
import pkgutil
import logging
from pathlib import Path

logger = logging.getLogger("ProcessorDiscovery")

def discover_all_processors():
    """
    自动递归挂载 processors 文件夹下的所有 python 模块。
    这确保了代码库里只要新增了一个 Processor 并带上 @registry.register
    就会在系统启动时自动可用，无需手动修改任何入口 import。
    """
    package_dir = Path(__file__).resolve().parent
    for _, module_name, is_pkg in pkgutil.walk_packages([str(package_dir)], prefix="processors."):
        if not is_pkg:
            try:
                importlib.import_module(module_name)
                logger.debug(f"Auto-imported processor module: {module_name}")
            except Exception as e:
                logger.warning(f"Failed to auto-import processor module {module_name}: {e}")

# 模块初始化时触发动机
discover_all_processors()
