# -*- coding: utf-8 -*-
from abc import ABC, abstractmethod
from typing import Dict, Any

from core.context import Context


class BaseProcessor(ABC):
    """
    所有的化学业务逻辑、大模型交互、向量清洗，都必须继承这个基类。
    实现 process 方法，对输入进来的 Context 对象进行修改。
    """
    def __init__(self, **kwargs):
        """配置中心传入的 kwargs 参数会被直接透传到这里"""
        self.config: Dict[str, Any] = kwargs

    @abstractmethod
    def process(self, context: Context) -> Context:
        """
        处理逻辑。
        如果发生不可恢复的错误，请调用 context.mark_invalid(reason) 
        并可以提早 return context。
        """
        pass
