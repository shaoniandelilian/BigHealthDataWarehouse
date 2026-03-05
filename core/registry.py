# -*- coding: utf-8 -*-
from typing import Dict, Type


class ProcessorRegistry:
    """
    轻量级插件注册表。
    所有继承自 BaseProcessor 的业务类，都可以通过 @register("名字") 注册进这里。
    Pipeline 调度器只认名字，完全解耦。
    """
    _registry: Dict[str, Type] = {}

    @classmethod
    def register(cls, name: str):
        def wrapper(processor_class: Type):
            if name in cls._registry:
                raise ValueError(f"Processor '{name}' has already been registered!")
            cls._registry[name] = processor_class
            return processor_class
        return wrapper

    @classmethod
    def get(cls, name: str) -> Type:
        if name not in cls._registry:
            raise KeyError(f"Processor '{name}' is not found in the registry.")
        return cls._registry[name]

    @classmethod
    def list_all(cls) -> list:
        return list(cls._registry.keys())

# 全局单例
registry = ProcessorRegistry()
