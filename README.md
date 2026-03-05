# ChemRAG-Flow: Real-Time Config-Driven Data Pipeline

**ChemRAG-Flow** 是一个面向化学及生物医学大模型场景的**高性能、高可用、插件化**的数据清洗与向量入库准实时流水线。

本项目同时支持“**化学生成特征工程流水线**”与“**PDF长文解析特征提取流水线**”两条并行的预设链路，并自带**人工验证 (Human-in-the-Loop)** 断点续传功能。

---

## 🚀 1. 快速启动 (Quick Start)

### 1.1 环境准备
```bash
# 核心与 API 网关依赖包
pip install requests pyyaml pydantic fastapi uvicorn

# [链路 1: 化学分子式处理依赖]
# 注意: 在某些纯净环境下，推荐使用 conda install -c conda-forge rdkit
pip install rdkit torch transformers pymilvus

# [链路 2: 获取并解析 PDF 文档依赖]
pip install PyMuPDF img2pdf Pillow vllm
```

### 1.2 环境变量配置
```bash
# 注入您的大模型调度密钥
export DEEPSEEK_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxx"
```

---

## ⚙️ 2. 流水线装配模版 (Pipeline Presets)

系统已经为您内置了两套完全独立的**预设编排配置模板**。运行不同的项目不再需要修改主代码，一切由 `configs/*.yaml` 决定：

### 预设一：核心化学分子链路 (`configs/pipeline_chemicals.yaml`)
用途：针对短文本字典，通过大模型提取 `Source/Function` 字段，随后清洗标准分子 `SMILES`，并进行 1024 维 BGE 向量生成与 Milvus 库落盘。
**配置文件算子流转：**
`DeepSeekExtractor` $\to$ `SmilesStandardizer` $\to$ `[HumanReviewPause(可选)]` $\to$ `BgeEmbedder` $\to$ `MilvusLoader`

### 预设二：非结构化文档 PDF 链路 (`configs/pipeline_pdf.yaml`)
用途：针对学术论文或科研财报 PDF 文件。使用极高资源利用率的挂载 `vLLM` 的本地 `DeepSeek-OCR` 抽取，对 Markdown 进行定长滑动视窗切块（Chunking），最终批量生成特征并落盘。
**配置文件算子流转：**
`PdfOcrProcessor` $\to$ `MarkdownChunker` $\to$ `[HumanReviewPause(可选)]` $\to$ `BgeEmbedder` $\to$ `MilvusLoader`

---

## 🚥 3. 【核心 API】常驻后台网关与数据接入

为了在工程中投入生产规模使用，本项目抛弃了传统的“跑一次 Python 文件就退出”的旧模式，提供基于 `FastAPI` 的高性能常驻内存网关。

### 3.1 启动 API 网关引擎

您可以指定启动哪一条流水线作为您的主服务挂载在内存中（需进入对应的虚拟环境）：

```bash
# [推荐] 启动化学分子长驻服务，监听 8001 端口
conda activate rag-embed
export DEEPSEEK_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxx"
python main.py serve --config configs/pipeline_chemicals.yaml --port 8001

# [推荐] 启动 PDF 解析长驻服务，监听 8000 端口

conda activate deepseek-ocr
export DEEPSEEK_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxx"
python main.py serve --config configs/pipeline_pdf.yaml --port 8000
```
*(提示: 如果想在后台静默持久运行，可使用 `nohup python main.py serve ... &`)*

### 3.2 外部接入单条数据验证 (同步调试)

服务启动后，您可以使用同步接口进行单步阻塞调用。**系统会一直等待大模型提取和向量库录入全部完成，再返回成功报文。**
⚠️ **必填参数踩坑警告**：如果是化学管线，`raw_smiles` 必须被原封不动地放进 `metadata` 层级里，否则引擎第二阶段（RDKit 清洗）将无法抓取它！

```bash
# 向化学流水线发送一条测试数据
curl -X POST http://127.0.0.1:8001/api/v1/ingest/sync \
     -H "Content-Type: application/json" \
     -d '{
           "id": "chem-test-01",
           "name": "异构甜菊苷",
           "metadata": {
               "raw_smiles": "CC(=O)OC1=CC=CC=C1C(=O)O"
           },
           "raw_data": {
               "原始描述": "甜菊苷同分异购物，具有更高的甜度"
           }
         }'
```

### 3.3 大批量 CSV 数据灌流代码 (异步高并发落地)

如果是几万、几十万行 CSV 处理任务，**禁止使用同步接口**（否则单线程会极其缓慢甚至超时断开）。请使用专为高吞吐设计的 **异步非阻塞接入**（`/api/v1/ingest/async`）。

您可以新建一个干净的 Python 脚本（不依赖本仓库环境），用以下模板疯狂将您的 CSV 数据推送给网关引擎：

```python
import pandas as pd
import requests

# 您的本地原始脏 CSV
df = pd.read_csv("my_huge_chemicals.csv")

API_URL = "http://127.0.0.1:8001/api/v1/ingest/async"

for idx, row in df.iterrows():
    payload = {
        "id": f"batch-data-{idx}",
        "name": str(row.get("Compound_Name", "Unknown")),
        "metadata": {
            # 必须传入此处供流水线第 2 步去清洗，如果 CSV 里这个字段叫 "SMILES"，请映射过来
            "raw_smiles": str(row.get("SMILES", ""))
        },
        "raw_data": {
            # 把所有可能对大模型 (DeepSeek) 有帮助的乱七八糟描述全扔这里面
            "context": str(row.get("Description", ""))
        }
    }
    
    # 异步请求，瞬间返回！引擎将在后台队列里慢慢消化
    resp = requests.post(API_URL, json=payload)
    print(f"Sent {idx}, status: {resp.status_code}")
```

### 3.4 人工审核断点续发引擎 (Review & Resume)

如果配置文件中装配了 `- name: "HumanReviewPause"` 算子，引擎会在处理到这一步时**立刻暂停**，并将这根数据的记忆存进本地 `logs/pending_reviews.db` 中。人工此时介入：

**接口 A：拉取当前数据库中等待人工审批的数据**
```http
GET http://127.0.0.1:8001/api/v1/review/pending?limit=20
```
返回一个清晰的数组，包含了需要验证修改内容的元信息（比如，抽取出来的配方或者解析错误的片段）。

**接口 B：人工修改完毕后提交，指令流水线继续跑并入库！**
```http
POST http://127.0.0.1:8000/api/v1/review/submit/{提取的数据_ID}
Content-Type: application/json

{
    "metadata": {
        "deepseek_raw_content": "[已人工将错误的氨基改回正确的苯基]"
    }
}
```
引擎接到这个 POST，会从冻结池里取出这条暂停的流水线载体，把您修正后的对象覆盖掉原有的脏数据，并从 `BgeEmbedder` 开始接着往下流（避开前面昂过的大模型提取步骤），最终优雅进入 Milvus 向量库！

---

## 📌 4. 离线工具包 (Offline Tools)

即使不借助网关系统，您也可以通过 `main.py` 触发底层的批量跑批任务：
1. 本地小数据流仿真测试：
   `python main.py test -c configs/pipeline_chemicals.yaml`
2. 本地 CSV 单表精准塞入：
   `python main.py batch_csv --file /path/to/data.csv -c configs/pipeline_chemicals.yaml`
3. 本地 PDF 目录自动化盲扫入库：
   `python main.py batch_pdf --dir /path/to/papers/ -c configs/pipeline_pdf.yaml`

---

## 🎉 5. 成功演示 (Success Demonstration)

通过以下完整步骤，您可以**见证一条脏数据瞬间走完 DeepSeek提取 -> RDKit重组 -> BGE向量化 -> Milvus落盘 的全过程**：

### ➡️ 步骤 1：启动后台服务集群 (Terminal 1)
打开第一个终端窗口，激活核心隔离环境，并拉起化学生产线 API 服务：
```bash
# 1. 激活环境
conda activate rag-embed

# 2. (可选) 声明您的 DeepSeek API Key。
# 注意：如果您已经在 configs/pipeline_chemicals.yaml 里写死了 api_key: "sk-...", 这步可以省略！
export DEEPSEEK_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxx"

# 3. 启动 API 网关监听 8001 端口
python main.py serve --config configs/pipeline_chemicals.yaml --port 8001
```

### ➡️ 步骤 2：发送数据 (Terminal 2)
打开另一个全新的终端窗口，发送以下 JSON 测试有效载荷：
```bash
curl -X POST http://127.0.0.1:8001/api/v1/ingest/sync \
     -H "Content-Type: application/json" \
     -d '{
           "id": "csv-test-01",
           "name": "异构甜菊苷",
           "metadata": {
               "raw_smiles": "CC(=O)OC1=CC=CC=C1C(=O)O"
           },
           "raw_data": {
               "原始描述": "甜菊苷同分异购物，具有更高的甜度"
           }
         }'
```

### ⬅️ 输出 (The Output)
*(不到 10 秒后，您的终端将完美打出涵盖所有维度的落盘回执！)*
```json
{
  "status": "success",
  "message": "Data processed and stored successfully.",
  "id": "csv-test-01",
  "metadata_snapshot": {
    "raw_smiles": "CC(=O)OC1=CC=CC=C1C(=O)O",
    "deepseek_raw_content": "Source: Isosteviol is a diterpenoid derivative obtained from the leaves of the stevia plant...\n\nFunction: Isosteviol functions as a non-caloric sweetener and exhibits a range of pharmacological activities...",
    "Standardized_SMILES": "CC(=O)OC1=C(C(=O)O)C=CC=C1",
    "Connectivity_SMILES": "CC(=O)OC1=C(C(=O)O)C=CC=C1",
    "InChI": "InChI=1S/C9H8O4/c1-6(10)13-8-5-3-2-4-7(8)9(11)12/h2-5H,1H3,(H,11,12)",
    "InChIKey": "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"
  }
}
```

---

## 🏢 6. 企业级增强架构 (Enterprise Integration)

本项目深度集成了工业级中间件，不仅提升了系统性能，更展示了**分布式、可观测、高性能**的架构深度。

### 6.1 Redis 缓存与性能飞跃 (Caching)
*   **LLM 缓存**: 利用 Redis 对大模型提取结果进行缓存（基于模型+实体名的 Hash）。
*   **性能实测**:
    *   **首次查询 (AI 提取)**: ~20.69s
    *   **二次命中 (Redis)**: **~0.78s (提升约 96%)**
*   **成本控制**: 为相同实体的重复入库节省了 100% 的大模型 Token 开销。
*   *(注: 系统内置 Smart-Mock 模式，若 Redis 未启动将自动降级为进程内内存缓存。)*

### 6.2 Kafka 分布式人工审核 (Event-Driven HITL)
*   **架构解耦**: 当流水线触发 `HumanReviewPause` 时，任务被序列化投递至 Kafka Topic `chemrag-pending-reviews`。
*   **异步闭环**: 支持通过 `services/distributed_worker.py` 监听审核结果。审核人员在任何终端提交修改后，Worker 自动唤醒流水线完成入库。
*   **削峰填谷**: 即使上游有海量并发数据，Kafka 也能确保审核任务不丢失、不溢出。

### 6.3 Prometheus 系统监控 (Observability)
*   **实时埋点**: 全局集成 `prometheus-client` 埋点。
*   **监控接口**: 访问 `http://127.0.0.1:8001/metrics` 即可获取：
    *   `chemrag_pipeline_processed_total`: 各管道吞吐量统计（成功/失败/被拦截）。
    *   `chemrag_processor_duration_seconds`: 各算子处理时延分布。
    *   `chemrag_cache_hits_total`: Redis 缓存命中率监控。

> [!IMPORTANT]
> 这一套 **FastAPI + Kafka + Redis + Prometheus + Milvus** 的组合方案，是工业级 AI 中台的标准参考架构，极具商业落地与简历展示价值。

