# ChemRAG-Flow: Real-Time Config-Driven Data Pipeline

**ChemRAG-Flow** 是一个面向化学及生物医学大模型场景的**高性能、高可用、插件化**的数据清洗与向量入库准实时流水线。

---

## 🚀 1. 快速启动 (Quick Start)

### 1.1 环境准备
```bash
# 核心与 API 网关依赖包
pip install requests pyyaml pydantic fastapi uvicorn flask

# [链路 1: 化学分子式处理依赖]
# 注意: 在某些纯净环境下，推荐使用 conda install -c conda-forge rdkit
pip install rdkit torch transformers pymilvus sentence-transformers

# [链路 2: 获取并解析 PDF 文档依赖]
pip install PyMuPDF img2pdf Pillow vllm magic-pdf pymupdf4llm
```

### 1.2 环境变量配置
```bash
# 注入您的大模型调度密钥 (以提供多重管道混合模型分析能力)
export DEEPSEEK_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxx"
export QWEN_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxx"
export KIMI_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxx"
```

---

## ⚙️ 2. 流水线装配模版 (Pipeline Presets)

当前已实现四套完全独立的**预设编排配置模板**。运行不同的项目不再需要修改主代码，一切由 `configs/*.yaml` 决定：

### 预设一：核心化学分子链路 (`configs/pipeline_chemicals.yaml`)
用途：针对短文本字典，通过大模型提取 `Source/Function` 字段，随后清洗标准分子 `SMILES`，并进行向量生成与 Milvus 库落盘。

### 预设二：非结构化文档 PDF 链路 (`configs/pipeline_pdf.yaml`)
用途：针对学术论文或科研财报 PDF 文件。使用极高资源利用率的挂载 `vLLM` 的本地 `DeepSeek-OCR` 抽取，进行定长滑动视窗切块。

### 预设三：本地离线 MinerU 端到端 PDF 解析链路 (`configs/pipeline_doc_ai.yaml`)
用途：实现从复杂排版 PDF 抽取公式、表格、清洁 Markdown，到语义与结构混合切分。

### 🌟 预设四：【最新力作】混合流控增强版链路 (`configs/pipeline_legacy_enhanced.yaml`)
用途：结合先进的非阻塞 Pipeline 引擎以及高度复杂的定制化业务需求构建而成的终极产物，既拥有最新架构的吞吐量与热插拔自适应状态管理，同时也完全兼容旧版极限界限清洗能力。
**配置文件算子流转：**
`MinerUOCRProcessor` (并发OCR) $\to$ `HybridAdvancedChunkerProcessor` (包含LaTeX数学公式占位保护与空格压缩机制) $\to$ `MultiLLMFilterProcessor` (DeepSeek+Qwen+Kimi 三体大语言模型层级漏斗并行过滤) $\to$ `HumanReviewPause` (强制挂起系统并转交切片级人工审核) $\to$ `YuanEmbedderProcessor` (KaLM 高维语义向量化与故障安全兜底) $\to$ `MilvusTypeLoader` (异步向量落库防崩溃版)

---

## 🚥 3. 【新功能】真可视化 Web 流控网关

除了底层的基于 FastAPI 的纯接口调用，现在引入了全新的**Web 大屏可视化网关 (`streaming/web_upload_gateway.py`)**。

### 3.1 启动可视化流控大屏

它会自动依托于底层的轻量追踪库（SQLite `pipeline_states.db`），将耗时极长的全流程 Pipeline 状态动态投射到网页端：
```bash
# 启动 Web Gateway（默认绑定 5001 端口）
python streaming/web_upload_gateway.py
```
**访问:** `http://127.0.0.1:5001` 或您的远程设备IP地址（例如 `http://172.20.8.28:5001`）。
- **极速上传:** 直接拖拽文件，引擎将瞬间创建一个新的 UUID 时空位点打入后台异步线程。
- **实时监控:** 仪表盘将展示您的文件正在流经哪个算子（解析 OCR、大模型漏斗...），并在结束后标注各层级的精确耗时。当流水线出错，更会把原始错误信息暴露在全屏供快速纠错。

### 3.2 切片颗粒度的人工干预审核 (Human-in-the-loop)
配置了 `HumanReviewPause` 拦截指令后，一旦面临极度开销大的向 Milvus 集群写入，引擎会**立刻暂停当前文档的进程**并将上下文冷冻至 `pending_reviews.db` 中生息！
- 从主面板点击 **[👁️ 进入人工审核工作台]** (`/review`)
- 面对大模型层层清洗并吐出的密密麻麻的结构切片，您可以体验上帝视角的控制：
    1. **手动修改**：如果觉得抽取略带瑕疵，文本框直接编辑覆盖。
    2. **精准切片打回**：对某个无法拯救或者含混不清的切块单独点击 **❌ 驳回此块**，它将变红销毁，跳过送显！
    3. 一键「🗑️ 直接丢弃整份文档」。
    4. 点击「✅ 保存修改并放行」，引擎将被即时从断头台唤醒，**带着你修正并剔除后的纯净块**，再次杀向 `YuanEmbedderProcessor` 高维嵌入池并直飞 `Milvus` 落盘！

---

## � 4. 远程数据库纯净运维指北

在可视化页面之外，如果你希望通过纯终端黑客般的进行系统的巡检与核实：

### 4.1 访问本地 SQLite 实时流状态追踪库
```bash
# 进入总体状态追踪数据库 (记录各个文档正在处于什么算子进度，耗时情况)
sqlite3 data/pipeline_states.db

# 检查记录表
sqlite> .mode column
sqlite> .headers on
sqlite> SELECT run_id, global_status, updated_at FROM pipeline_legacy_enhanced_state ORDER BY updated_at DESC LIMIT 5;
sqlite> .quit
```

### 4.2 访问远端 Milvus 万亿级特征数据库
通过提供的一个快刀斩乱麻检查脚本来嗅探：
```bash
# 你可以直接在终端通过写一个 python 脚本查询
cat << 'EOF' > check_milvus.py
from pymilvus import connections, Collection, utility

connections.connect(alias="default", host="47.98.227.81", port="19530")
collection_name = "test_pdf" # 根据 yaml 中更改
if utility.has_collection(collection_name):
    col = Collection(collection_name)
    col.load()
    print(f"✅ 集合 [{collection_name}] 数据总量: {col.num_entities} 条")
else:
    print("❌ 集合不存在！")
EOF

python check_milvus.py
```

---

## 🏢 5. 企业级增强架构底座简述 (Enterprise Base)

本项目不仅仅是一套“脚本组合”，更是一套底层经过重重检验的大型中间件微缩版：
1. **Redis 缓存与性能飞跃**: 对大模型过滤网络等环节，利用哈希机制智能屏蔽重复请求开销。
2. **Kafka 分布式削峰填谷**: 底蕴支持。若上游迎来千万并发文件，允许将暂停动作反序列化塞回 `chemrag-pending-reviews` Topic，交给几十台消费机器抢夺。
3. **环境故障自愈与防御性编程**: 对算子内部（如丢失大模型包、丢失 Milvus 连接等）均实现了异常捕获机制，可根据缺失选择使用哑巴占位符（如 768 维 0 向量）放行并留下日志警告，以确保管线整体绝不崩溃（Never Panic）。
# BigHealthDataWarehouse
