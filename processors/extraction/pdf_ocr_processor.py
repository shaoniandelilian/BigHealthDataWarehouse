# -*- coding: utf-8 -*-
import io
import logging
from typing import Dict, Any, List

from core.context import Context
from core.registry import registry
from processors.base import BaseProcessor

@registry.register("PdfOcrProcessor")
class PdfOcrProcessor(BaseProcessor):
    """
    负责将本地 PDF 文件，利用 DeepSeek-OCR 和 vLLM 引擎，抽取并解析为 Markdown 纯文本。
    核心逻辑封装自 /data/wuteng/DeepSeek-OCR-main/DeepSeek-OCR-master/DeepSeek-OCR-vllm/run_dpsk_ocr_pdf.py
    
    注意：在初始化时，如果 lazy_load=False，会尝试启动 vLLM 大模型占用显存。
    为了兼容轻量级环境流转，如果在无卡环境运行或模型路径不对，会自动降级为抛错且隔离（断路器生效）。
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.logger = logging.getLogger("PdfOcrProcessor")
        self.model_path = self.config.get("model_path", "/data/wuteng/DeepSeek-OCR-main/DeepSeek-OCR-master/DeepseekOCRForCausalLM")
        self.dpi = self.config.get("dpi", 144)
        self.lazy_load = self.config.get("lazy_load", True)
        
        self.llm = None
        self.sampling_params = None
        
        # 为了不拖垮整个 api_server 启动速度，允许在使用此算子的第一条数据进入时再懒加载模型
        if not self.lazy_load:
            self._init_vllm_engine()

    def _init_vllm_engine(self):
        """挂载 GPU 大模型（高门槛操作，容易因为显卡被占用而崩掉，因此做隔离保护）"""
        if self.llm is not None:
            return
            
        try:
            self.logger.info(f"⏳ Booting Up VLLM Engine for DeepSeek-OCR from {self.model_path}")
            # 下面是完全照抄原有代码库里的 import，通过 try 捕捉缺失的依赖
            import torch
            from vllm.model_executor.models.registry import ModelRegistry
            from vllm import LLM, SamplingParams
            import sys
            import os
            
            # 因为原始代码依赖了它自己的库 (deepseek_ocr 等)，必须动态加入到系统路径里
            original_code_dir = "/data/wuteng/DeepSeek-OCR-main/DeepSeek-OCR-master/DeepSeek-OCR-vllm"
            if original_code_dir not in sys.path:
                 sys.path.append(original_code_dir)
                 
            from deepseek_ocr import DeepseekOCRForCausalLM
            from process.ngram_norepeat import NoRepeatNGramLogitsProcessor

            # 注册模型
            ModelRegistry.register_model("DeepseekOCRForCausalLM", DeepseekOCRForCausalLM)
            
            # 兼容旧环境变量设置
            if torch.version.cuda == '11.8':
                os.environ["TRITON_PTXAS_PATH"] = "/usr/local/cuda-11.8/bin/ptxas"
                
            self.llm = LLM(
                model=self.model_path,
                hf_overrides={"architectures": ["DeepseekOCRForCausalLM"]},
                block_size=256,
                enforce_eager=False,
                trust_remote_code=True,
                max_model_len=4096,  # 缩小以节省显存，原为 8192
                swap_space=0,
                max_num_seqs=2,      # 限制并发
                tensor_parallel_size=1,
                gpu_memory_utilization=0.6, # 限制显存，防 OOM
                disable_mm_preprocessor_cache=True
            )
            
            logits_processors = [NoRepeatNGramLogitsProcessor(ngram_size=20, window_size=50, whitelist_token_ids={128821, 128822})]
            self.sampling_params = SamplingParams(
                temperature=0.0,
                max_tokens=4096,
                logits_processors=logits_processors,
                skip_special_tokens=False,
                include_stop_str_in_output=True,
            )
            self.logger.info("✅ VLLM Engine booted successfully!")
        except ImportError as e:
            self.logger.error(f"❌ Missing dependencies for vLLM or local code: {e}")
            raise RuntimeError(f"Cannot initialize OCR Engine: {e}")
        except Exception as e:
            self.logger.error(f"❌ Failed to load VLLM: {e}")
            raise RuntimeError(f"VLLM boot failed: {e}")

    def process(self, context: Context) -> Context:
        file_path = context.raw_data.get("file_path")
        if not file_path or not file_path.lower().endswith(".pdf"):
            # 不是 PDF，不需要 OCR 放行
            return context
            
        try:
            # 懒加载防呆
            if self.llm is None:
                self._init_vllm_engine()
                
            import fitz
            from PIL import Image
            import sys
            
            original_code_dir = "/data/wuteng/DeepSeek-OCR-main/DeepSeek-OCR-master/DeepSeek-OCR-vllm"
            if original_code_dir not in sys.path:
                 sys.path.append(original_code_dir)
            from process.image_process import DeepseekOCRProcessor
            from config import PROMPT
            
            self.logger.info(f"📄 Processing PDF via DeepSeek-OCR: {file_path}")
            
            # ============ 1. PDF 切片变图片 (PyMuPDF) ============
            doc = fitz.open(file_path)
            zoom = self.dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            
            images = []
            for i in range(doc.page_count):
                page = doc[i]
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                if img.mode != 'RGB':
                     img = img.convert('RGB')
                images.append(img)
            doc.close()
            
            # ============ 2. 组装 vLLM 格式化输入 ============
            prompt = PROMPT
            batch_inputs = []
            processor = DeepseekOCRProcessor()
            for img in images:
                cache_item = {
                    "prompt": prompt,
                    "multi_modal_data": {"image": processor.tokenize_with_images(images=[img], bos=True, eos=True, cropping=False)}
                }
                batch_inputs.append(cache_item)
                
            # ============ 3. vLLM 推理 ============
            outputs_list = self.llm.generate(batch_inputs, sampling_params=self.sampling_params)
            
            # ============ 4. 组装为巨长的 Markdown Text ============
            full_markdown = ""
            for page_idx, output in enumerate(outputs_list):
                 content = output.outputs[0].text
                 if '<｜end▁of▁sentence｜>' in content:
                     content = content.replace('<｜end▁of▁sentence｜>', '')
                 full_markdown += f"\n<!-- Page {page_idx + 1} -->\n"
                 full_markdown += content
                 
            # 保存到 Context 中，供下游的 MarkdownChunker 接着切！
            context.metadata["full_markdown"] = full_markdown
            self.logger.info(f"✅ Extracted OCR Markdown: length {len(full_markdown)}")
                 
        except Exception as e:
            # 即便崩了，也只会废掉当前这条 PDF，绝不会搞垮 Pipeline 守护进程
            context.mark_invalid(f"Pdf OCR Processing failed: {e}")
            
        return context
