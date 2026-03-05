# -*- coding: utf-8 -*-
import logging
import math
import random
import time
from typing import Dict, Any

import requests
from rdkit import Chem

from core.context import Context
from core.registry import registry
from processors.base import BaseProcessor
from utils.rate_limiter import RateLimiter

@registry.register("SmilesStandardizer")
class SmilesStandardizer(BaseProcessor):
    """
    负责调用 PubChem 和本地 RDKit 清洗、规范化 SMILES。
    对应原 `Smilestandize.py` 的处理逻辑。
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.pubchem_url = self.config.get(
            "url", "https://pubchem.ncbi.nlm.nih.gov/rest/pug/standardize/smiles/SDF"
        )
        self.max_retries = self.config.get("max_retries", 3)
        self.timeout_sec = self.config.get("timeout_sec", 30)
        
        # 为了防止被封 IP，我们在初始化时复用一个全局 RateLimiter
        # 如果是 Celery worker，这里应放在进程级别或 Redis 共享锁限制
        rps = self.config.get("rate_limit", 3)  # 注意：降频至 3 保护账号
        self.limiter = RateLimiter(rps)
        self.session = requests.Session()
        
        self.logger = logging.getLogger("SmilesStandardizer")

    def _is_blank(self, x) -> bool:
        if x is None: return True
        if isinstance(x, float) and math.isnan(x): return True
        s = str(x).strip()
        return s == "" or s.lower() == "nan"

    def process(self, context: Context) -> Context:
        # 这个组件往往在 Pipeline 中游，假设上游产生了一个待处理的 SMILES 存放在 metadata
        smiles = context.metadata.get("raw_smiles") or (
            context.raw_data if isinstance(context.raw_data, str) else None
        )
        
        if self._is_blank(smiles):
            context.mark_invalid("Missing SMILES to standardize.")
            return context

        smiles = str(smiles).strip()
        last_err = None

        self.logger.info(f"Standardizing SMILES via PubChem: {smiles[:30]}...")
        for attempt in range(self.max_retries):
            try:
                self.limiter.acquire()
                r = self.session.post(
                    self.pubchem_url, data={"smiles": smiles}, timeout=self.timeout_sec
                )
                
                if r.status_code in (429, 500, 502, 503, 504):
                    raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
                    
                r.raise_for_status()
                sdf_bytes = r.content

                suppl = Chem.SDMolSupplier()
                suppl.SetData(sdf_bytes, removeHs=False)
                mols = [m for m in suppl if m is not None]
                if not mols:
                    context.mark_invalid("PubChem Standardization returned empty or unparseable SDF.")
                    return context
                    
                m = mols[0]
                try:
                    Chem.Kekulize(m, clearAromaticFlags=True)
                except Exception:
                    pass

                m = Chem.RemoveHs(m)
                
                # 双模态 SMILES
                smiles_iso = Chem.MolToSmiles(m, canonical=True, isomericSmiles=True, kekuleSmiles=True)
                smiles_conn = Chem.MolToSmiles(m, canonical=True, isomericSmiles=False, kekuleSmiles=True)
                
                try:
                    from rdkit.Chem import inchi
                    inchi_str = inchi.MolToInchi(m)
                    inchikey_str = inchi.InchiToInchiKey(inchi_str)
                except Exception:
                    inchi_str = inchikey_str = None

                # 提取出的结果保存回 Context
                context.metadata["Standardized_SMILES"] = smiles_iso
                context.metadata["Connectivity_SMILES"] = smiles_conn
                context.metadata["InChI"] = inchi_str
                context.metadata["InChIKey"] = inchikey_str
                
                self.logger.info("Successfully standardized SMILES.")
                return context

            except Exception as e:
                last_err = str(e)
                sleep_s = (0.8 * (2 ** attempt)) + random.uniform(0, 0.4)
                time.sleep(sleep_s)

        context.mark_invalid(f"SmilesStandardizer Exceeded Retries: {last_err}")
        return context
