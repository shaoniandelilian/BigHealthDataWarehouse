#!/usr/bin/env python3
"""
增强版 Web UI Gateway
融合老版本优雅的上传界面与新版本 (Event-Driven) 大语言模型流水线。
自动读取 SQLite tracked states 进行前端进度展示。
"""

import os
import sys
import uuid
import yaml
import threading
import sqlite3
import requests
from urllib.parse import urlparse
from pathlib import Path
from datetime import datetime

from flask import Flask, render_template_string, request, redirect, url_for, flash

sys.path.insert(0, '.')
from core.context import Context
from core.pipeline import Pipeline
from core.state_manager import global_state_manager
from core.review_store import ReviewStore

app = Flask(__name__)
app.secret_key = 'knowledge-base-pipeline-secret-v2'

UPLOAD_FOLDER = Path("./data/uploads")
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'doc', 'txt', 'md', 'png', 'jpg', 'jpeg'}

# ======= 加载 Pipeline =======
config_path = "configs/pipeline_legacy_enhanced.yaml"
pipeline_name = os.path.basename(config_path)
with open(config_path, "r", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)
pipeline_engine = Pipeline(cfg["pipeline_steps"], pipeline_name=pipeline_name)

# 初始化专门的 Review Store
review_store = ReviewStore()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

REVIEW_HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>人工数据审核中心</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f4f6f9; min-height: 100vh; padding: 20px; }
        .container { max-width: 900px; margin: 0 auto; }
        .header { text-align: center; color: #1e3c72; padding: 30px 0; }
        .header h1 { font-size: 2em; margin-bottom: 10px; }
        .card { background: white; border-radius: 12px; padding: 25px; margin-bottom: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); }
        .btn { display: inline-block; padding: 10px 20px; color: white; border: none; border-radius: 6px; font-size: 0.9em; cursor: pointer; text-decoration: none;}
        .btn-primary { background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); }
        .chunk-box { margin-top: 15px; padding: 15px; border: 1px solid #e9ecef; border-radius: 8px; background: #fdfdfd;}
        textarea { width: 100%; height: 80px; margin-top: 8px; padding: 10px; border: 1px solid #ccc; border-radius: 6px; font-family: inherit; resize: vertical;}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔍 人工数据审核中心</h1>
            <p>检查流水线预处理的分块，修改后放行或直接驳回</p>
        </div>
        
        <div style="margin-bottom: 20px;">
            <a href="/" class="btn btn-primary" style="margin-bottom: 10px;">⬅️ 返回实时处理大盘</a>
        </div>
        
        {% if records %}
            {% for record in records %}
            <div class="card">
                <h3 style="color:#333; margin-bottom: 10px;">📄 任务标识: {{ record.id[:15] }}...</h3>
                <p style="color:#666; font-size:0.9em; margin-bottom:20px;">挂起时间: {{ record.created_at }}</p>
                
                <form action="/review/action/{{ record.id }}" method="POST">
                    {% set chunks = record.metadata.get('chunks', []) %}
                    <div style="max-height: 500px; overflow-y: auto; padding-right:10px;">
                    {% for c in chunks %}
                        <div class="chunk-box" id="chunk_container_{{ loop.index0 }}">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;">
                                <label style="font-weight: 600; font-size: 0.9em; color:#444;">块 #{{ loop.index }} (长度: {{ c.text|length }})</label>
                                <div>
                                    <input type="checkbox" name="keep_{{ loop.index0 }}" id="keep_{{ loop.index0 }}" value="yes" checked style="display:none;">
                                    <button type="button" class="btn" style="padding: 4px 10px; font-size: 0.8em; background: #dc3545;" onclick="toggleDiscard({{ loop.index0 }})" id="btn_toggle_{{ loop.index0 }}">❌ 驳回此块</button>
                                </div>
                            </div>
                            <textarea name="chunk_{{ loop.index0 }}" id="textarea_{{ loop.index0 }}">{{ c.text }}</textarea>
                        </div>
                    {% endfor %}
                    </div>
                    
                    <div style="margin-top:25px; display:flex; gap:15px;">
                        <button type="submit" name="action" value="approve" class="btn" style="background:#28a745; flex:1; font-size:1em;">✅ 保存修改并放行【未被驳回】的块</button>
                        <button type="submit" name="action" value="reject_all" class="btn" style="background:#dc3545; flex:1; font-size:1em;">🗑️ 直接丢弃整份文档</button>
                    </div>
                </form>
            </div>
            {% endfor %}
            <script>
                function toggleDiscard(idx) {
                    var chk = document.getElementById('keep_' + idx);
                    var btn = document.getElementById('btn_toggle_' + idx);
                    var txt = document.getElementById('textarea_' + idx);
                    var box = document.getElementById('chunk_container_' + idx);
                    if (chk.checked) {
                        chk.checked = false;
                        btn.innerHTML = '✅ 恢复此块';
                        btn.style.background = '#28a745';
                        txt.style.opacity = '0.3';
                        txt.readOnly = true;
                        box.style.background = '#fbe2e4'; // light red background for disabled blocks
                    } else {
                        chk.checked = true;
                        btn.innerHTML = '❌ 驳回此块';
                        btn.style.background = '#dc3545';
                        txt.style.opacity = '1';
                        txt.readOnly = false;
                        box.style.background = '#fdfdfd';
                    }
                }
            </script>
        {% else %}
            <div class="card" style="text-align: center; padding: 50px; color: #888;">
                <h2>🎉 目前工作台清空</h2>
                <p style="margin-top: 10px;">干得漂亮！没有任何需要人工审核的数据块了。</p>
            </div>
        {% endif %}
    </div>
</body>
</html>
"""

# HTML 模板复用旧版，做少量适配
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>企业级知识库端到端管线</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); min-height: 100vh; padding: 20px; }
        .container { max-width: 900px; margin: 0 auto; }
        .header { text-align: center; color: white; padding: 40px 0; }
        .header h1 { font-size: 2.5em; margin-bottom: 10px; }
        .header p { opacity: 0.9; font-size: 1.1em; }
        .card { background: white; border-radius: 16px; padding: 30px; margin-bottom: 20px; box-shadow: 0 10px 40px rgba(0,0,0,0.1); }
        .upload-area { border: 3px dashed #ddd; border-radius: 12px; padding: 60px 40px; text-align: center; transition: all 0.3s; cursor: pointer; }
        .upload-area:hover { border-color: #1e3c72; background: #f8f9ff; }
        .upload-icon { font-size: 4em; color: #ccc; margin-bottom: 20px; }
        .btn { display: inline-block; padding: 12px 30px; background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); color: white; border: none; border-radius: 8px; font-size: 1em; cursor: pointer; width: 100%; margin-top: 20px;}
        input[type="file"] { display: none; }
        .job-item { display: flex; align-items: center; padding: 15px; border-bottom: 1px solid #eee; }
        .job-info { flex: 1; }
        .job-name { font-weight: 500; color: #333; margin-bottom: 5px; }
        .job-meta { font-size: 0.85em; color: #666; }
        .status-badge { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 0.85em; font-weight: 500;}
        .status-running { background: #cce5ff; color: #004085; animation: pulse 1.5s infinite;}
        .status-completed { background: #d4edda; color: #155724; }
        .status-failed { background: #f8d7da; color: #721c24; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        .stage-details { display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap; }
        .stage-item { padding: 6px 12px; border-radius: 20px; font-size: 0.8em; background: #f8f9fa; border: 1px solid #e9ecef; }
        .stage-success { background: #e8f5e9; border-color: #4caf50; color: #388e3c; }
        .stage-running { background: #e3f2fd; border-color: #2196f3; color: #1976d2; }
        .stage-failed { background: #f8d7da; border-color: #dc3545; color: #721c24; }
        .stage-cost { margin-left:5px; font-size: 0.9em; opacity: 0.7;}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📚 知识库上传处理中心</h1>
            <p>基于新一代纯异步热插拔架构的增强流水线</p>
        </div>
        
        <div class="card">
            <form method="POST" action="/upload" enctype="multipart/form-data" id="uploadForm">
                <div class="upload-area" id="dropZone" onclick="document.getElementById('fileInput').click()">
                    <div class="upload-icon">📁</div>
                    <div id="uploadText" style="color: #666; font-size: 1.1em;">点击或拖拽多个文件到此处立刻开始批量处理</div>
                    <input type="file" name="files" id="fileInput" accept=".pdf,.docx,.doc,.txt,.md,.png,.jpg,.jpeg" multiple>
                </div>
                <button type="submit" class="btn">🚀 立刻冲入管线处理</button>
            </form>
            <div style="margin-top: 15px; text-align: center;">
                <form method="POST" action="/upload_url" id="urlUploadForm" style="display: flex; gap: 10px;">
                    <input type="url" name="url" placeholder="或者粘贴公网文件 URL 链接 (如 http://.../xxx.pdf)" style="flex:1; padding: 12px; border-radius: 8px; border: 1px solid #ccc;" required>
                    <button type="submit" class="btn" style="width: auto; margin-top: 0; padding: 0 20px;">🌐 抓取入库</button>
                </form>
            </div>
        </div>

        <div class="card">
            <h2 style="display: flex; justify-content: space-between; align-items: center;">
                <span>📋 实时流水线处理追踪</span>
                <a href="/review" class="btn" style="width: auto; padding: 8px 15px; margin: 0; background: #e83e8c; font-size: 0.9em;">
                    👁️ 进入人工审核工作台 
                </a>
            </h2>
            {% if jobs %}
                <div style="margin-top:20px;">
                    {% for job in jobs %}
                    <div class="job-item">
                        <div class="job-info">
                            <div class="job-name">🎯 {{ job.source_file }} 
                                <span style="font-size:0.8em; color:#999;">[Run ID: {{ job.run_id[:8] }}...]</span>
                            </div>
                            <div class="job-meta">进入时间: {{ job.created_at }}</div>
                            <div class="stage-details">
                                {% for proc_name, proc_state in job.processor_states.items() %}
                                    <div class="stage-item stage-{{ proc_state.status }}">
                                        {{ proc_name }} 
                                        {% if proc_state.cost > 0 %} <span class="stage-cost">({{ "%.1f"|format(proc_state.cost) }}s)</span> {% endif %}
                                    </div>
                                {% endfor %}
                            </div>
                            {% if job.error_message %}
                                <div style="color:red; font-size:0.8em; margin-top:5px; max-width:600px; white-space:nowrap; overflow:hidden; text-overflow: ellipsis;">{{ job.error_message }}</div>
                            {% endif %}
                        </div>
                        <span class="status-badge status-{{ job.global_status }}">{{ job.global_status }}</span>
                    </div>
                    {% endfor %}
                </div>
            {% else %}
                <div style="text-align: center; padding: 40px; color: #999;">通道空闲，暂无文书在运行。</div>
            {% endif %}
        </div>
    </div>
    <script>
        const dropZone = document.getElementById('dropZone'), fileInput = document.getElementById('fileInput'), uploadText = document.getElementById('uploadText');
        
        // 点击选择文件
        fileInput.addEventListener('change', () => { 
            if (fileInput.files.length > 0) {
                uploadText.innerHTML = `已选择 <b>${fileInput.files.length}</b> 个文件等待冲洗...<br><span style="font-size:0.8em">(${Array.from(fileInput.files).map(f => f.name).slice(0, 3).join(', ')}${fileInput.files.length>3?'...':''})</span>`;
            } 
        });

        // 拖拽事件支持
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.style.borderColor = '#1e3c72';
            dropZone.style.background = '#f8f9ff';
        });
        
        dropZone.addEventListener('dragleave', (e) => {
            e.preventDefault();
            dropZone.style.borderColor = '#ddd';
            dropZone.style.background = 'transparent';
        });
        
        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.style.borderColor = '#ddd';
            dropZone.style.background = 'transparent';
            if (e.dataTransfer.files.length > 0) {
                fileInput.files = e.dataTransfer.files; // 赋值给 input
                // 手动触发 change 事件更新文字
                fileInput.dispatchEvent(new Event('change'));
            }
        });

        setInterval(() => window.location.reload(), 3000);
    </script>
</body>
</html>
"""

def get_jobs_from_sqlite():
    """从强大的轻量级追踪SQLite层实时抓取流水线跑图"""
    db_path = global_state_manager.db_path
    tbl_name = global_state_manager._get_table_name(pipeline_name)
    
    jobs = []
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            # 查实表存不存在
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (tbl_name,))
            if not cursor.fetchone(): return []
            
            cursor.execute(f"SELECT * FROM {tbl_name} ORDER BY updated_at DESC LIMIT 15")
            rows = cursor.fetchall()
            
            for row in rows:
                row_dict = dict(row)
                proc_states = {}
                # 动态把所有的热插拔 _status 列洗出来
                for key, val in row_dict.items():
                    if key.endswith("_status"):
                        p_name = key.replace("_status", "")
                        cost_val = row_dict.get(f"{p_name}_cost", 0.0)
                        if val != 'pending':
                             proc_states[p_name] = {"status": val, "cost": cost_val}
                
                jobs.append({
                    "run_id": row_dict["run_id"],
                    "source_file": row_dict["source_file"],
                    "global_status": row_dict["global_status"],
                    "created_at": row_dict["created_at"],
                    "error_message": row_dict.get("error_message"),
                    "processor_states": proc_states
                })
    except Exception as e:
        print(f"Error reading SQLite: {e}")
    return jobs

@app.route('/')
def index():
    jobs = get_jobs_from_sqlite()
    return render_template_string(HTML_TEMPLATE, jobs=jobs)

@app.route('/review')
def review_page():
    records = review_store.get_pending_records(limit=20)
    return render_template_string(REVIEW_HTML_TEMPLATE, records=records)

@app.route('/review/action/<context_id>', methods=['POST'])
def review_action(context_id):
    action = request.form.get('action')
    ctx = review_store.get_and_delete_context(context_id)
    if not ctx:
        return redirect(url_for('review_page'))
        
    if action == 'reject_all' or action == 'reject':
        # 丢弃处理，只需更新状态即可，无需继续执行
        ctx.global_status = "rejected"
        global_state_manager.update_global_status(ctx.run_id, ctx.pipeline_name, "rejected")
        return redirect(url_for('review_page'))
        
    if action == 'approve':
        # 更新用户手动修改的 chunk 文本，并剔除被驳回的块
        chunks = ctx.metadata.get("chunks", [])
        final_chunks = []
        for i, c in enumerate(chunks):
            keep = request.form.get(f"keep_{i}")
            if keep == "yes":
                new_text = request.form.get(f"chunk_{i}")
                if new_text is not None:
                    c["text"] = new_text
                final_chunks.append(c)
        
        ctx.metadata["chunks"] = final_chunks
        
        # 恢复流水线执行
        ctx.is_pending_review = False
        start_idx = ctx.paused_at_step if ctx.paused_at_step > 0 else 0
        threading.Thread(target=pipeline_engine.run, args=(ctx,), kwargs={"start_index": start_idx}).start()
        
    return redirect(url_for('review_page'))

def _background_pipeline_worker(file_path: Path, filename: str):
    """后台直接调我们牛逼的流引擎"""
    ctx = Context(raw_data={
        "id": f"upload-{uuid.uuid4().hex[:8]}",
        "file_path": str(file_path),
        "data_type": "document"
    })
    try:
        final_ctx = pipeline_engine.run(ctx)
        event_id = ctx.run_id
        if getattr(final_ctx, 'is_pending_review', False):
            review_store.save_pending_context(event_id, final_ctx)
            print(f"⏸️ Pipeline paused for review for {filename}")
        elif final_ctx.is_valid:
            print(f"✅ Pipeline completed successfully for {filename}")
        else:
            print(f"❌ Pipeline failed for {filename}. Errors: {final_ctx.errors}")
    except Exception as e:
        print(f"🔥 Catastrophic failure in background job {filename}: {e}")

@app.route('/upload', methods=['POST'])
def upload():
    # 支持多文件同时上传 (适配 multiple attribute)
    files = request.files.getlist('files')
    if not files or files[0].filename == '':
        return redirect(url_for('index'))
        
    for file in files:
        if file and allowed_file(file.filename):
            save_path = UPLOAD_FOLDER / file.filename
            file.save(save_path)
            # 每一个文件新开启一个线程丢入流水线长列
            threading.Thread(target=_background_pipeline_worker, args=(save_path, file.filename)).start()
            
    return redirect(url_for('index'))

@app.route('/upload_url', methods=['POST'])
def upload_url():
    target_url = request.form.get('url')
    if not target_url:
        return redirect(url_for('index'))
         
    # 提取文件名
    filename = os.path.basename(urlparse(target_url).path)
    if not filename or '.' not in filename:
        filename = f"downloaded_{uuid.uuid4().hex[:6]}.pdf"
         
    save_path = UPLOAD_FOLDER / filename
    
    try:
        # 下载文件并保存
        resp = requests.get(target_url, stream=True, timeout=30)
        resp.raise_for_status()
        with open(save_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192): 
                if chunk: f.write(chunk)
                
        # 丢入流水线长列
        threading.Thread(target=_background_pipeline_worker, args=(save_path, filename)).start()
    except Exception as e:
        print(f"❌ Failed to download from URL {target_url}: {e}")
        
    return redirect(url_for('index'))

if __name__ == '__main__':
    print(f"🚀 增强混合流控终端 GUI 启动: http://0.0.0.0:5001")
    app.run(host='0.0.0.0', port=5001, debug=False)
