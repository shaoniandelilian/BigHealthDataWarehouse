# -*- coding: utf-8 -*-
import os
import time
import base64
import logging
from typing import Dict, Any, Optional

from fastapi import FastAPI, HTTPException, Request
import uvicorn
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("LocalMinerUServer")

app = FastAPI(title="Local MinerU PDF Parse API", version="1.0.0")

class ParseRequest(BaseModel):
    pdf_path: str
    output_dir: str
    parse_method: str = "auto"
    
@app.post("/api/v1/parse")
async def parse_pdf(req: ParseRequest):
    """
    接收本地 PDF 路径并调用 magic-pdf 进行解析。
    这完全模拟了云端 MinerU 的接口行为，但运行在本地 127.0.0.1
    """
    abs_pdf_path = os.path.abspath(req.pdf_path)
    abs_output_dir = os.path.abspath(req.output_dir)
    
    if not os.path.exists(abs_pdf_path):
        raise HTTPException(status_code=400, detail=f"PDF file not found at: {abs_pdf_path}")
        
    os.makedirs(abs_output_dir, exist_ok=True)
    
    base_name = os.path.splitext(os.path.basename(abs_pdf_path))[0]
    
    try:
        # 在这里局部导入，防止启动时如果没有安装 magic-pdf 导致服务起不来
        try:
             from magic_pdf.tools.common import do_parse
        except ImportError:
             raise HTTPException(status_code=500, detail="magic-pdf library is not installed on this machine. Run `pip install magic-pdf[full]`.")

        with open(abs_pdf_path, "rb") as f:
            pdf_bytes = f.read()

        logger.info(f"🧠 [MinerU Server] Starting parsing for: {base_name} (method={req.parse_method})")
        start_time = time.time()
            
        do_parse(
            output_dir=abs_output_dir,
            pdf_file_name=base_name,
            pdf_bytes_or_dataset=pdf_bytes,
            model_list=[],
            parse_method=req.parse_method
        )
        
        duration = time.time() - start_time
        logger.info(f"✅ [MinerU Server] Parsing completed in {duration:.2f}s")
        
        # 查找生成的 markdown
        local_md_path = os.path.join(abs_output_dir, base_name, req.parse_method, f"{base_name}.md")
        if not os.path.exists(local_md_path):
            local_md_path = os.path.join(abs_output_dir, base_name, f"{base_name}.md")
            
        return {
            "code": 200,
            "msg": "success",
            "data": {
                "file_name": base_name,
                "output_dir": abs_output_dir,
                "markdown_path": local_md_path,
                "duration": duration
            }
        }
        
    except Exception as e:
        logger.error(f"❌ [MinerU Server] Parse failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    # 使用 0.0.0.0 可以让外部网络（如果需要）访问，默认端口 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)
