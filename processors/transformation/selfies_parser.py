# -*- coding: utf-8 -*-
import logging
from core.context import Context
from core.registry import registry
from processors.base import BaseProcessor

@registry.register("SelfiesParser")
class SelfiesParser(BaseProcessor):
    """
    负责将 SELFIES 字符串解析为标淮 SMILES 字符串的插件。
    对应于老脚本 /wuji/Selfiestosmiles.py 的功能。
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.logger = logging.getLogger("SelfiesParser")
        self.strict_mode = self.config.get("strict_mode", True)

    def process(self, context: Context) -> Context:
        # 首先确认传入的字段里是否有 SELFIES (无论是叫 selfies 还是 raw_selfies)
        selfies_str = None
        if isinstance(context.raw_data, dict):
            selfies_str = context.raw_data.get("raw_selfies") or context.raw_data.get("selfies")
            
        if not selfies_str:
            selfies_str = context.metadata.get("raw_selfies")
            
        # 如果根本没有 SELFIES 数据，说明这条数据不需要这个算子处理，直接原样放行，绝对不报错！
        if not selfies_str:
            return context
            
        try:
            import selfies as sf
            from rdkit import Chem
            
            self.logger.info(f"Decoding SELFIES to SMILES...")
            # 解码
            smiles_str = sf.decoder(selfies_str)
            
            # 使用 RDKit 标准化
            molecule = Chem.MolFromSmiles(smiles_str)
            if molecule is None:
                raise ValueError(f"RDKit无法解析解码后的SMILES: {smiles_str}")
                
            smiles_result = Chem.MolToSmiles(molecule)
            
            # 【关键解耦点】：把洗好的 SMILES 塞进包里。
            # 下一个算子 (SmilesStandardizer) 就能直接拿到干净的 raw_smiles 继续往下流转了！
            context.metadata["raw_smiles"] = smiles_result
            self.logger.info(f"Successfully decoded SELFIES: {smiles_result[:30]}...")
            
        except ImportError:
            context.mark_invalid("Missing 'selfies' library. Please run: pip install selfies")
        except Exception as e:
            if self.strict_mode:
                context.mark_invalid(f"Failed to decode SELFIES: {e}")
            else:
                self.logger.warning(f"Failed to decode SELFIES, but strict_mode=False. Error: {e}")
            
        return context
