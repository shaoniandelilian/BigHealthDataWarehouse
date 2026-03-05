# -*- coding: utf-8 -*-
from typing import List, Optional

import torch
from transformers import AutoTokenizer, AutoModel

class SimpleBgeEmbeddings:
    """
    一个极简的 BGE 向量封装类，不依赖 sentence-transformers。
    在解耦架构中提供基础模型能力。
    """
    def __init__(
        self,
        model_name: str = "BAAI/bge-large-zh-v1.5",
        device: Optional[str] = None,
        max_length: int = 512,
        normalize: bool = True,
        add_instruction: bool = True,
        local_files_only: bool = False,
    ):
        self.model_name = model_name
        self.max_length = max_length
        self.normalize = normalize
        self.add_instruction = add_instruction
        self.local_files_only = local_files_only

        if device is None:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)

        try:
            self.tokenizer = AutoTokenizer.from_pretrained(model_name, local_files_only=local_files_only)
            self.model = AutoModel.from_pretrained(model_name, local_files_only=local_files_only)
        except OSError as e:
            raise OSError(str(e) + "\nModel load failed, check paths and offline mode.")

        self.model.to(self.device)
        self.model.eval()

    @staticmethod
    def _mean_pool(last_hidden_state: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
        mask = attention_mask.unsqueeze(-1).expand(last_hidden_state.size()).float()
        summed = (last_hidden_state * mask).sum(dim=1)
        summed_mask = mask.sum(dim=1).clamp(min=1e-9)
        return summed / summed_mask

    def embed_query(self, text: str) -> List[float]:
        if not text:
            return []
        
        texts = [text]
        if self.add_instruction:
            texts = [f"为这个句子生成表示以用于检索相关文章：{t}" for t in texts]

        enc = self.tokenizer(
            texts, padding=True, truncation=True, max_length=self.max_length, return_tensors="pt"
        ).to(self.device)

        with torch.no_grad():
            outputs = self.model(**enc)
            token_embeddings = outputs.last_hidden_state
            sentence_embeddings = self._mean_pool(token_embeddings, enc["attention_mask"])

            if self.normalize:
                sentence_embeddings = torch.nn.functional.normalize(sentence_embeddings, p=2, dim=1)

        return sentence_embeddings.cpu().tolist()[0]
