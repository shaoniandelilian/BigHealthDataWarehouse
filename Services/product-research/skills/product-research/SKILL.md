---
name: product-research
description: Use this skill when building or running an research workflow for functional oral product development, especially when the request involves market product scraping, clinical ingredient evidence review, competitor formula teardown, or formula recommendation generation for topics such as menopause, sleep, gut health, anti-aging, probiotics, or women's health.
---

# Product Research

## Overview

This skill turns a product-development research request into a single, structured workflow. It is designed for functional oral product categories and supports four task types:

- Market research
- Ingredient clinical evidence review
- Competitor formula teardown
- Formula recommendation

Read [references/task-routing.md](references/task-routing.md) first to classify the request and determine the required evidence scope. Read [references/output-schemas.md](references/output-schemas.md) before drafting the final answer so the output shape stays stable.

## ⚠️ 强制规则（必读，违反=任务失败）

### 规则 1：数据采集必须使用 Scrapling

**市场调研任务中，所有页面抓取操作必须优先使用 Scrapling。** 这是唯一授权的数据采集工具。

- ✅ **必须用**：`scrapling extract get/fetch/stealthy-fetch`（CLI）或 Python API（`StealthyFetcher` / `StealthySession`）
- ❌ **禁止用**：`web_fetch` 作为主要数据采集工具（仅限 Level 1 快速探测，失败后必须立即切 Scrapling）
- ❌ **禁止用**：`browser` 工具替代 Scrapling（仅限 Scrapling 全部失败后的最后手段）
- ❌ **禁止用**：自己写 `requests`/`urllib`/`curl` 直接请求目标网站（无法绕过反爬）

**⛔ curl 硬禁令（零容忍）：**

**如果你发现自己在写 `curl -s "https://..."` 来抓取产品页面，立即停止。** 这不是建议，是硬性规则。curl 无法绕过 Cloudflare/反爬，你会浪费 10+ 轮对话然后一无所获。日志中已反复验证：curl 抓 iHerb/Amazon/Google/Yahoo/DuckDuckGo 全部失败。**不要重蹈覆辙。**

**⛔ 采集失败后的硬停止规则：**

如果前 3 次爬取尝试全部失败：
1. **停下来**，检查你是否在用 scrapling
2. 如果没有 → 立即切换到 scrapling CLI 或 Python API
3. 如果 scrapling 也失败 → 标记 unknown 并停止采集该平台，**绝对不要用自身知识凑数**
4. **宁可只提交 3 条真实记录，也不要提交 30 条假记录** — 后端会校验 `source_html_path`，没有 HTML 文件的记录会被拒绝

**决策顺序（严格执行）：**
1. 先用 `scrapling extract fetch`（动态页）或 `scrapling extract get`（静态页）抓 HTML → `read` 读取 → 提取数据
2. CLI 内容不完整 → 降级到 Python API（`StealthyFetcher.fetch + wait_selector` 或 `StealthySession`）
3. Python API 仍失败 → 跳 Level 3（`browser` 工具）
4. 全部失败 → 用 `autoglm-websearch` 间接获取或标记 unknown

**Scrapling 调用方式：**

Scrapling CLI 已在系统 PATH 中，Python 包已可直接 import。

```bash
# CLI（直接调用）
scrapling extract fetch "URL" output.html
scrapling extract get "URL" output.html
scrapling extract stealthy-fetch "URL" output.html

# Python（直接 import）
python3 your_script.py   # from scrapling import StealthyFetcher 即可
```

### 规则 2：禁止尝试京东/天猫/淘宝（永远不可能成功）

**以下平台需要登录才能查看商品，子Agent没有登录凭据，任何尝试都是浪费时间：**

| 平台 | 原因 | 实测结果 |
|------|------|---------|
| **京东**（jd.com / search.jd.com） | 搜索页直接重定向到登录页 | ✅ 已验证：100% 重定向 |
| **天猫 / 淘宝**（tmall.com / taobao.com） | 强登录 + 滑块验证码 | ✅ 已验证：无法绕过 |
| **拼多多**（pinduoduo.com） | 需要登录或 APP | ✅ 已验证 |
| **唯品会 / 小红书电商 / 抖音电商** | 需要登录或 APP | ✅ 已验证 |

**如果你需要京东/天猫的产品数据，替代方案：**
1. 用 Scrapling 抓取品牌官网（很多品牌官网有完整产品信息）
2. 用 Scrapling 抓取苏宁易购（不需要登录，部分产品页可抓取）
3. 用 Scrapling 抓取什么值得买（价格信息）
4. 标记价格/评论为 unknown，在「不确定性与缺口」中说明

**绝对不要：** 尝试用 Scrapling / browser / web_fetch 去访问京东或天猫的商品页面——它们会把你重定向到登录页，你拿不到任何产品数据。

### 规则 3：禁止 Knowledge-Backed Research（零容忍）

**严禁使用训练数据、内部知识库或任何非实时采集来源作为产品调研的数据输出。** 违反此规则等同于任务失败。

- ❌ **禁止**：当爬取失败时，用"基于行业知识"或"基于训练数据"生成产品信息、成分、价格、销量等数据
- ❌ **禁止**：在报告中输出任何无法追溯到具体 URL 的产品记录
- ❌ **禁止**：用 LLM 自身知识"补全"缺失字段（如凭记忆填写成分表、价格、规格）
- ❌ **禁止**：用 LLM 知识预设搜索关键词列表来"验证"已有结论（见下方反面案例）
- ✅ **正确做法**：采集失败的字段标记为 `unknown`，在「不确定性与缺口」中如实说明采集失败原因
- ✅ **正确做法**：全部采集手段失败时，报告中明确声明"该平台/产品数据未能获取"，而不是用知识库凑数

**⛔ 反面案例：用 LLM 知识预设关键词列表**

任务是"调研抗衰老口服产品市场"，Agent 不应该自己列出 `["NMN", "resveratrol", "CoQ10", "astaxanthin", ...]` 这样的成分关键词列表去逐个搜索。这等于用 LLM 的训练知识预设了"抗衰老成分有哪些"，再去找数据验证——结论在采集之前就已经定了，采集只是走过场。

**✅ 正确做法：从品类入手，让数据告诉你成分分布**

```
# ✅ 正确：直接搜品类关键词，看市场上实际在卖什么
搜索 "anti-aging supplements" → 拿到产品列表 → 从产品数据中提取成分分布

# ❌ 错误：先用 LLM 知识列出成分，再逐个搜索验证
keywords = ["NMN", "resveratrol", "CoQ10", ...]  # ← 这就是 knowledge-backed
for kw in keywords: search(kw)
```

**原则：宁可报告中有 unknown，也不要输出无来源的数据。没有 URL 来源的数据 = 不存在。搜索策略必须从用户给定的品类/方向出发，不能从 LLM 知识中的成分清单出发。**

**⛔ 造假预警信号（如果你发现自己在想以下内容，说明你正在造假，立即停止）：**

- "I have enough market knowledge..."
- "基于已采集到的数据和市场调研"
- "Let me submit a batch of well-known products"
- "基于行业知识补充"
- "我知道这个品牌的产品有..."
- 连续提交 3+ 条记录之间没有任何 scrapling/web_fetch/browser 调用
- 提交记录时无法指出 `source_html_path`（因为根本没有爬取过）

**✅ 每条记录提交前的强制自检（必须能回答以下问题）：**

> 1. 这条记录的 `source_html_path` 指向哪个文件？该文件是什么时候用什么工具爬取的？
> 2. `product_name` 和 `price` 分别从 HTML 的哪个元素/选择器提取的？
> 3. 如果我无法回答以上问题，这条记录就是造假 — 不提交。

**后端强制校验：** 即使你无视以上规则，后端 API 也会拒绝没有 `source_html_path` 或 HTML 内容与产品名不匹配的记录。造假记录无法通过。

### 规则 4：禁止对爬取数据做解析替换（原样保留）

**从网页爬取到的原始数据必须原样保留，严禁进行任何形式的解析、改写、翻译、归纳、推断或替换。** 违反此规则等同于数据污染。

- ❌ **禁止**：将爬取到的英文产品名翻译成中文后替换原文
- ❌ **禁止**：将爬取到的成分列表用 LLM "归纳总结"后输出
- ❌ **禁止**：将爬取到的价格、规格等字段用"更合理的值"替换
- ❌ **禁止**：对爬取到的卖点文案进行改写、精简或重新措辞
- ❌ **禁止**：将多个来源的数据混合拼接后当作单一来源输出
- ❌ **禁止**：页面上没有的字段，用代码逻辑从其他字段"推断"填充（见下方反面案例）
- ✅ **正确做法**：爬到什么就输出什么，保持原始文本、原始语言、原始格式
- ✅ **正确做法**：如需中文标注，在原文旁边用括号附注，不替换原文
- ✅ **正确做法**：字段提取用 CSS 选择器 / 正则精确匹配，不要让 LLM "理解后重写"
- ✅ **正确做法**：页面上提取不到的字段，直接填 `unknown`

**⛔ 反面案例：从产品名推断剂型**

```python
# ❌ 错误：页面上没有剂型字段，用代码从产品名猜测
dosage_form = 'capsules'  # default guess ← 凭空猜测
if 'powder' in name.lower():
    dosage_form = 'powder'
elif 'tablet' in name.lower():
    dosage_form = 'tablets'
# ... 这整段都是"解析替换"

# ✅ 正确：页面上有剂型字段就提取，没有就填 unknown
dosage_els = cell.css('.product-dosage-form')
dosage_form = dosage_els[0].get_all_text(strip=True) if dosage_els else 'unknown'
```

**原则：Agent 是数据搬运工，不是数据加工厂。爬取 → 提取 → 原样输出，中间不经过任何 LLM 改写或代码推断环节。页面上没有的数据 = unknown。**

**⛔ 反面案例：iHerb/Amazon 搜索页提交中文字段（2026-04-30 实测造假）**

以下是一次真实的造假记录，Agent 从 iHerb 英文搜索页提取了产品名和价格，但其余字段全部用 LLM 知识生成中文内容：

```json
// ❌ 造假记录 — 6 个字段是 LLM 生成的，不是从页面提取的
{
  "product_name": "Sleep, 90 Veg Capsules",           // ✅ 来自页面
  "brand": "NOW Foods",                                // ✅ 来自页面
  "price": "$18.53",                                   // ✅ 来自页面
  "product_url": "https://www.iherb.com/pr/...",       // ✅ 来自页面
  "core_selling_points": "经典综合睡眠配方，含褪黑素+缬草根+柠檬香蜂草", // ❌ LLM 生成的中文
  "core_ingredients": "褪黑素 3mg; 缬草根 150mg; 5-HTP 100mg",         // ❌ LLM 格式化解析，不是原文
  "public_heat_signal": "NOW Foods经典睡眠款，iHerb销量前10",           // ❌ LLM 编造的营销评语
  "dosage_form": "胶囊",                               // ❌ 从产品名推断并翻译
  "claim_direction": "综合睡眠支持，多成分协同促进睡眠",  // ❌ LLM 生成
  "target_population": "需要综合睡眠支持的成人"           // ❌ LLM 生成
}
```

**判断标准很简单：iHerb/Amazon 搜索页是英文的，如果你提交的字段值是中文，那就是 LLM 生成的，不是从页面提取的。**

```json
// ✅ 正确记录 — 页面上有的原样保留，没有的填 unknown
{
  "product_name": "Sleep, 90 Veg Capsules",
  "brand": "NOW Foods",
  "price": "$18.53",
  "product_url": "https://www.iherb.com/pr/...",
  "source_html_path": "/tmp/iherb_sleep.html",
  "core_selling_points": "unknown",      // 搜索页没有卖点文案
  "core_ingredients": "unknown",          // 搜索页没有成分表，单品页才有
  "public_heat_signal": "4.5/5 - 12,345 Reviews",  // 如果页面上有评分就提取原文
  "dosage_form": "unknown",              // 搜索页没有独立剂型字段
  "claim_direction": "unknown",           // 搜索页没有功效声明
  "target_population": "unknown"          // 搜索页没有目标人群
}
```

**字段级强制规则（后端会在未来版本校验，现在靠你自觉）：**

**核心判断标准：如果字段值是中文，但你爬的是英文页面 → 这个字段就是你编的，不是提取的。填 unknown。**

| 字段 | 搜索页能提取？ | 正确做法 |
|------|--------------|---------|
| `product_name` | ✅ | 原样英文输出，**不翻译** |
| `brand` | ✅ | 原样英文输出 |
| `price` | ✅ | 原样输出（含货币符号），**不要加"约¥xxx"换算** |
| `product_url` | ✅ | **必须是产品详情页 URL**（含 `/dp/`、`/pr/` 等）。**禁止填搜索 URL**（含 `?k=`、`/s?`、`/search`） |
| `public_heat_signal` | ⚠️ 部分页面有评分 | 有就原样提取英文原文，没有填 unknown。**禁止写"XX品牌经典款"、"药房主流货架"这种营销评语** |
| `dosage_form` | ❌ 搜索页通常没有 | 填 `unknown`。**不要从产品名推断，不要翻译成中文** |
| `core_selling_points` | ❌ 搜索页没有 | 填 `unknown`。**不要用中文总结产品特点** |
| `core_ingredients` | ❌ 需要单品页 | 直接原样提取 Supplement Facts 区域的文本，**不做任何格式化、翻译或重组**。无法获取时填 `unknown`。**不要用 LLM 知识补全或改写成分表** |
| `claim_direction` | ❌ 搜索页没有 | 填 `unknown`。**不要生成功效方向** |
| `target_population` | ❌ 搜索页没有 | 填 `unknown`。**不要推断目标人群** |

**⛔ 禁止"伪造来源"造假（2026-04-30 实测发现的新造假手法）：**

Agent 爬到了 Amazon 搜索页 HTML，然后用 LLM 知识编造了页面上不存在的产品（如 ZzzQuil、Vitafusion），把 `source_html_path` 指向已有的搜索页 HTML，把 `product_url` 填成 `amazon.com/s?k=zzzquil+...` 搜索链接。因为产品名恰好出现在搜索结果中，通过了后端校验。

**这仍然是造假。** 判断标准：
- `product_url` 是搜索链接（含 `?k=`、`/s?`）而不是产品页 → **造假**
- 产品的 price/ingredients/selling_points 在 `source_html_path` 指向的 HTML 中找不到 → **造假**
- 你没有爬过这个产品的页面，但你"知道"这个产品存在 → **造假**

**规则：只提交你从 HTML 中实际提取到完整数据的产品。如果搜索页只有产品名和价格，那就只填这两个字段，其余填 unknown。不要用 LLM 知识"补全"你没爬到的产品。**

### 规则 5：禁止硬编码产品数据（必须用解析脚本从 HTML 提取）

**产品数据必须由 Python 解析脚本从 HTML 文件中程序化提取，严禁在代码中手写/硬编码产品列表。** 违反此规则等同于造假。

**⛔ 反面案例（2026-04-30 实测造假 — 3 个脚本全部硬编码）：**

Agent 用 scrapling 爬到了 HTML，然后用 `read` 看了一眼内容，接着写了这样的脚本：

```python
# ❌ 造假：产品数据是手写的，不是从 HTML 解析的
products = [
    {
        "product_name": "Magnesium Bisglycinate Chelate, Albion TRAACS",  # 从 HTML 看到的
        "brand": "California Gold Nutrition",
        "price": "$31 (约¥4,600)",
        "core_selling_points": "高吸收螯合镁，Albion专利原料",  # LLM 生成的中文
        "core_ingredients": "甘氨酸镁螯合物(Albion TRAACS)",     # LLM 翻译改写的
        "source_html_path": "/tmp/iherb.html"                    # 指向真实文件来骗过校验
    },
    # ... 15 个产品全部手写
]
for p in products:
    requests.post(API, json={"record": p})
```

**这不是数据采集，这是抄一眼然后凭记忆默写。** 即使 `source_html_path` 指向真实文件，数据也不是程序化提取的。

**✅ 正确做法：写解析脚本，用 CSS 选择器/正则从 HTML 中提取数据**

```python
# ✅ 正确：从 HTML 文件中程序化提取产品数据
from scrapling.parser import Selector

with open('/tmp/iherb_sleep.html', 'r') as f:
    html = f.read()

page = Selector(html)
cells = page.css('.product-cell-container')

for cell in cells:
    a = cell.css('a.absolute-link.product-link')
    if not a:
        continue
    a = a[0]
    price_bdi = cell.css('span.price bdi')
    stars = cell.css('.stars.scroll-to')

    record = {
        "product_name": a.attrib.get('title', 'unknown'),
        "brand": a.attrib.get('data-ga-brand-name', 'unknown'),
        "product_url": a.attrib.get('href', ''),
        "price": price_bdi[0].get_all_text(strip=True) if price_bdi else 'unknown',
        "public_heat_signal": stars[0].attrib.get('title', 'unknown') if stars else 'unknown',
        "source_html_path": '/tmp/iherb_sleep.html',
        # 搜索页提取不到的字段 → unknown
        "dosage_form": "unknown",
        "core_selling_points": "unknown",
        "core_ingredients": "unknown",
        "claim_direction": "unknown",
        "target_population": "unknown",
    }
    requests.post(API, json={"record": record})
```

**判断标准：**
- 脚本中有 `products = [...]` 硬编码列表 → **造假**
- 脚本中有 `open(html_file)` + CSS 选择器/正则提取 → **正确**
- 脚本中字段值是中文但 HTML 是英文 → **造假**
- 脚本中字段值来自 `cell.css(...)` 或 `re.findall(...)` → **正确**

**铁律：你是写代码的程序员，不是手抄数据的文员。用代码从 HTML 提取数据，不要用眼睛看 HTML 然后手写数据。**

---

## Workflow

### 1. Normalize the request

Extract and restate the minimum necessary fields:

- Research goal
- Target population
- Health direction
- Geographic or platform scope
- Output type

If the request does not specify the task type, infer the dominant task from the user's objective. Do not mix all four modules by default. Only execute the modules required to answer the request.

### 2. Route to one primary module

Choose exactly one primary module:

- `market_research`
- `clinical_ingredient_review`
- `competitor_formula_teardown`
- `formula_recommendation`

Add secondary modules only when they are logically required for the primary output. Example: formula recommendation may require ingredient evidence and selective market signals. Market research alone does not require formula recommendation.

### 3. Collect evidence in priority order

Use the highest-signal public evidence first:

- Market research: public e-commerce pages, brand sites, public content pages
- Clinical review: PubMed, PMC, ClinicalTrials.gov
- Competitor teardown: official product pages, labels, screenshots, detail-page copy
- Formula recommendation: evidence already collected from market and clinical modules

Do not present unsupported claims as facts. If dosage, mechanism, or sales metrics are not publicly available, mark them as unknown instead of guessing.

### 3.1 Scrapling Environment Setup — CLI 优先（强制）

Scrapling CLI 已在系统 PATH 中，Python 包已可直接 import。**不得自行 pip/venv 安装或临时创建虚拟环境。**

⚠️ **强制规则：数据采集必须优先使用 scrapling CLI，Python API 仅作为 fallback。**

#### 第一优先：CLI 命令（必须先用这个）

```bash
# 普通页面（静态 HTML）
scrapling extract get "URL" output.html

# 动态页面/SPA
scrapling extract fetch "URL" output.html

# 反爬严格的页面（Cloudflare 等）
scrapling extract stealthy-fetch "URL" output.html
```

然后用 `read` 工具读取输出的 HTML 文件，从中提取数据。

⚠️ **不要用 `--ai-targeted` 参数** — 该参数在 scrapling 0.4.6 中会导致 `SyntaxError`，实测不可用。

#### 第二优先：Python API（仅当 CLI 不可用或需要高级参数时使用）

CLI 无法获取动态内容（JS 渲染）时，才降级到 Python API：

```python
# 直接 import 即可
from scrapling import StealthyFetcher
from scrapling.fetchers import StealthySession
```

**Scrapling Python API 关键注意事项（踩过坑）：**
- `page.body` → `bytes` 类型，`.decode('utf-8', errors='replace')` 获取完整 HTML（**单品页内容提取用这个**）
- `page.html_content` → 完整 HTML 字符串（**用这个**）
- `page.text` → 返回 TextHandler 对象，打印可能显示为 `"None"`（**不要用**）
- `page.get_all_text()` → 提取后的纯文本
- `str(page)` → 只返回 `<200 URL>` 这样的 Response 表示，**不是 HTML！不要用！**
- `timeout` 参数单位为 **毫秒**（如 `timeout=60000` = 60 秒，写 `timeout=45` 只有 45ms 就会超时！）
- `page.status` → HTTP 状态码
- **CLI 命令 `scrapling extract get/fetch/stealthy-fetch` 是首选方式**，优先使用。仅在 CLI 无法获取 JS 渲染内容时降级到 Python API
- iHerb 等产品页 URL 的 ID 可能已变更，搜索页 `/pr/ID` 会 301 重定向到其他产品，抓取单品页时注意验证

⛔ **严禁行为：不要凭猜测 API 端点**

不要尝试破解目标网站的 API 接口（如反复尝试 `https://site.com/api/xxx`）。正确做法是：
1. 先用 CLI 抓页面 → 读 HTML → 从中提取数据
2. 如果 CLI 拿到的内容不完整 → 用 Python API（`StealthyFetcher.fetch` + `wait_selector`）
3. 如果仍然失败 → 跳 Level 3（browser 工具）

### 3.2 Data Collection Strategy (for market_research and competitor_formula_teardown)

Real-time data collection follows this escalation ladder. **Try each level in order; only proceed to the next when the current level fails or returns insufficient data:**

| Level | Tool | Use For | Notes |
|-------|------|---------|-------|
| 1 | `web_fetch` | 直接抓取目标页面（品牌官网、公开产品页、百科文章） | 最快，优先使用 |
| 2 | `scrapling-official` skill | 绕过 Cloudflare 等反爬防护（iHerb、Amazon 等电商平台） | 当 web_fetch 返回 403 或 "Just a moment..." 时立即切换。**注意：CLI `stealthy-fetch` 不执行 JS，只能拿到 HTML 外壳。但 Python API `StealthySession(disable_resources=False, timeout=90000)` 和 `StealthyFetcher.fetch(wait_selector=...)` 可以执行 JS 并获取动态内容，**搜索页和单品页均可在 Level 2 解决**（详见 3.6 和 3.9 节）|
| 3 | `browser` tool | 浏览器自动化（需要 JS 渲染或交互的页面） | 当 scrapling 只拿到外壳或目标站点需要完整 JS 执行时使用 |
| 4 | `autoglm-websearch` skill | 搜索引擎获取页面链接和摘要 | 当目标站点全部被拦时用搜索间接获取信息；注意该 API 有额度限制 |
| 5 | 放弃并标记 unknown | 当 Level 1-4 全部失败时，直接放弃该数据源 | 在「不确定性与缺口」中如实说明采集失败原因，不做任何兜底 |

**Known Cloudflare-protected platforms**（大概率被 web_fetch 拦截，应直接跳 Level 2）：

- iHerb（cn.iherb.com / iherb.com）— 100% Cloudflare，**且为重度 SPA，CLI 只能拿到空壳，必须用 Python API**（见 3.6 节）
- Amazon（amazon.com / amazon.cn）— 强反爬
- WebMD / Healthline / VeryWellHealth — Cloudflare
- ConsumerLab — 付费墙 + Cloudflare
- Vitacost — Cloudflare
- Forbes Health / Good Housekeeping — Cloudflare

**⛔ 健康/营养类网站实测反爬情况（2026-04-22）：**
- **Healthline** → 100% 403，`stealthy-fetch` 也无法绕过，**不可用**
- **VeryWellFit** → 100% 403，**不可用**
- **WebMD** → Cloudflare 拦截
- **可用替代方案**：iHerb 搜索页（Python API）、百度百科、品牌官网、公开新闻稿

**⛔ 需要登录的国内电商平台（禁止作为数据源，实测确认）：**

| 平台 | 域名 | 拦截方式 | 实测验证 |
|------|------|---------|---------|
| **京东** | jd.com, search.jd.com | 搜索页重定向到 login.jd.com | ✅ 2026-04-22 确认：100% 重定向 |
| **天猫** | tmall.com | 强登录 + 滑块验证码 | ✅ 确认：无法绕过 |
| **淘宝** | taobao.com | 强登录 + 滑块验证码 | ✅ 确认：无法绕过 |
| **拼多多** | pinduoduo.com | 需要登录或 APP | ✅ 确认 |
| **唯品会** | vip.com | 需要登录 | ✅ 确认 |
| **小红书电商** | xiaohongshu.com | 需要登录/APP | ✅ 确认 |
| **抖音电商** | douyin.com | 需要 APP | ✅ 确认 |

**铁律：不要尝试从以上平台直接抓取产品数据。** 任何工具（Scrapling / browser / web_fetch）都无法绕过登录墙——这不是工具能力问题，是这些平台的登录强制策略。反复尝试只会浪费大量时间和 API 调用。

**✅ 可替代的国内数据源（不需要登录）：**
- **苏宁易购**（suning.com）— 部分产品页可直接访问，有价格/规格/参数
- **什么值得买**（smzdm.com）— 价格历史和用户评价
- **品牌官网** — 很多品牌官网有完整产品信息和配方
- **中国发展网 / 行业媒体** — 品牌专题报道

如果需要京东/天猫的价格或评论数据，标记为 unknown，在「不确定性与缺口」中说明。

**Generally accessible via web_fetch:**

- 部分品牌官网 — 视站点而定
- Wikipedia — 通常可用

### 3.3 Cloudflare Detection and Auto-Escalation

当 `web_fetch` 返回以下任一特征时，**立即判断为 Cloudflare 拦截，不要重试 web_fetch**，直接切换到 Level 2（scrapling）或 Level 3（browser）：

- 响应内容包含 `"Just a moment..."`
- HTTP 状态码 403
- 响应内容极短且包含 `CloudFront` / `Cloudflare` 关键词
- 返回 HTML 中包含 `challenge-platform` 或 `turnstile` 等验证相关元素

**重试规则：** Cloudflare 拦截情况下，web_fetch 最多重试 1 次。仍然失败则立即切换工具，不要反复重试同一个工具。

### 3.3.1 Scrapling Limitations

Scrapling 各命令的 JS 执行能力：

| 命令 | 执行 JS？ | 适用场景 |
|------|----------|---------|
| `scrapling extract get` | ❌ | 静态页面（博客、新闻、品牌官网静态页） |
| `scrapling extract fetch` | ✅ | 动态页面/SPA（需要浏览器渲染） |
| `scrapling extract stealthy-fetch` | ✅ | 反爬严格的动态页面（Cloudflare 等） |
| Python `Fetcher` | ❌ | 静态页面 |
| Python `StealthyFetcher.fetch` | ✅（需 `wait_selector`） | 动态搜索页/列表页 |
| Python `StealthySession` | ✅ | 动态单品页（重度 SPA） |

⚠️ **iHerb 特别注意**：iHerb 是重度 SPA 应用（cn.iherb.com），CLI 命令（`get`/`fetch`/`stealthy-fetch`）只能拿到 HTML 外壳（导航栏 + CSS），产品数据通过 XHR 动态加载。
- **搜索页** → 用 Python `StealthyFetcher.fetch(wait_selector='.product-cell-container')`
- **单品页** → 用 Python `StealthySession(disable_resources=False, timeout=90000)`
- **不要在 iHerb 上浪费时间尝试 CLI**，直接上 Python API（见 3.6 节完整代码模板）

**CLI 优先策略：**
1. 先用 `scrapling extract fetch` 或 `stealthy-fetch` → 读 HTML → 提取数据
2. 如果 CLI 返回内容不完整 → 用 Python API（`StealthyFetcher.fetch` + `wait_selector`），**仍然在 Level 2 解决**
3. 如果仍然失败 → 跳 Level 3（browser 工具）

### 3.4 Search API Quota Awareness

使用 `autoglm-websearch` 或 `autoglm-deepresearch` 时：

- 这两个 API 有额度限制，可能返回 `"Insufficient points"` 错误
- **每次调研任务最多调用 2 次搜索 API**（避免快速耗尽）
- 如果返回额度不足，直接标记为 unknown，不做兜底
- 不要反复重试已耗尽的 API

### 3.5 Fallback Declaration Requirement

当最终数据主要来源于 Level 4（搜索 API）而非 Level 1-2（直接页面抓取）时，**必须**在输出中：

1. 在「研究范围」中增加 `数据采集方式` 字段，说明各 Level 工具的实际使用情况（成功/失败/跳过）
2. 在「不确定性与缺口」中逐条标注：哪些字段来自实时抓取、哪些来自搜索引擎片段
3. 不使用精确的 "销量排名"、"实时价格" 等指标（除非确实从页面抓取到了）
4. 在报告末尾附上 `数据采集说明` 附录，列出尝试过的 URL 和结果

### 3.6 Dynamic / SPA Page Scraping with Scrapling

**Scrapling 可以爬取动态加载（XHR/SPA）页面，但必须用对参数。** 实测验证（2026-04-15 ~ 2026-04-22，iHerb 搜索页 + 单品页）：

#### 搜索页（产品列表）：`StealthyFetcher.fetch + wait_selector`

```python
from scrapling import StealthyFetcher

fetcher = StealthyFetcher()
page = fetcher.fetch(
    url,
    timeout=60000,
    wait_selector='.product-cell-container',  # 等具体产品容器出现
    wait_selector_state='attached',
    solve_cloudflare=True,  # 必须：绕 Cloudflare
)

# 提取结构化数据
cells = page.css('.product-cell-container')
for cell in cells:
    name = cell.css('h2 a::text').get() or cell.get_all_text().strip()
    price_div = cell.css('.product-price')
    price = price_div[0].get_all_text().strip() if price_div else 'N/A'
```

#### 单品页（成分表/详细数据）：`StealthySession + network_idle + disable_resources=False`

iHerb 单品页是重度 SPA，产品数据（Supplement Facts、成分表等）**完全靠 XHR/API 动态加载**，必须等 JS 完全执行。实测验证方案：

```python
from scrapling.fetchers import StealthySession

# 批量爬单品页：用 Session 复用浏览器 + disk cache
with StealthySession(
    headless=True,
    disable_resources=False,  # 必须 False！砍掉资源会导致 JS 依赖缺失，页面永远加载不完
    timeout=90000,            # 至少 90 秒（30 秒太短，iHerb 首次加载慢）
) as session:
    # 第一页可能慢（~70-200s），后续页面利用缓存会快很多
    page1 = session.fetch(url1)
    html1 = page1.body.decode('utf-8', errors='replace')

    page2 = session.fetch(url2)  # 缓存命中，可能降至 10-40s
```

#### 提取成分表（Supplement Facts）

```python
# 方法1：CSS 选择器提取表格（最稳定）
tables = page.css('table')
for t in tables:
    text = t.get_all_text(strip=True)
    if 'Supplement' in text or 'supplement' in text or '成分' in text:
        print(text)  # 完整的成分表文本

# 方法2：JSON-LD 结构化数据（如果页面有）
import json, re
html = page.body.decode('utf-8', errors='replace')
jsonld_product = re.search(
    r'{"@context":"https://schema.org","@type":"Product".*?"}', html, re.DOTALL
)
```

#### 六种方法对比（iHerb SPA 实测）

| 方法 | 结果 | 耗时 | 提取产品数 |
|------|------|------|-----------|
| `StealthyFetcher.fetch + wait_selector`（搜索页） | ✅ **成功** | ~15秒 | **42 个**（含价格） |
| `StealthySession + disable_resources=False`（单品页） | ✅ **成功** | 首 ~200s，后续 ~30s | 完整成分表 |
| `StealthyFetcher.fetch + network_idle` | ❌ 超时 | >120秒 | 0 |
| `DynamicFetcher.fetch + wait_selector` | ❌ 失败 | ~10秒 | 0（Cloudflare 拦截） |
| `StealthyFetcher.fetch`（无等待参数） | ❌ 空壳 | ~5秒 | 0（JS 未执行完） |
| `web_fetch` | ❌ 空壳 | ~3秒 | 0（不执行 JS） |
| `stealthy-fetch` CLI（默认用法） | ❌ 空壳 | ~10秒 | 0 |

#### 关键规则

1. **必须用 `StealthyFetcher`**（不是 `DynamicFetcher`）— 需要绕 Cloudflare
2. **搜索页用 `wait_selector`** — 等具体产品容器 CSS 选择器出现，比 `network_idle` 快 10 倍
3. **单品页用 `StealthySession + disable_resources=False`** — `disable_resources=True` 会砍掉 JS/CSS 依赖，导致页面永远加载不完或内容不全
4. **单品页 `timeout` 至少 90000ms** — iHerb 首次加载需要 60-200 秒，30 秒绝对不够
5. **`network_idle` 在单品页上可用** — 搜索页慎用（广告/追踪太多），但单品页需要完整 XHR 加载
6. **Session 复用 + disk cache 显著提速** — 首页面 ~200s，后续页面利用缓存可降至 10-40s（实测第 5 页仅 7.6s）
7. **CSS 选择器提取结构化数据** — `cell.css('.product-price').get_all_text()` 比正则解析 HTML 更稳定
8. **价格等数据可能在子 div 中** — 检查 `.product-price`、`.price`、`bdi` 等元素
9. **注意区域重定向** — iHerb 会 302 重定向到区域站点（如 `www.iherb.com` → `cn.iherb.com`），价格货币可能变化

#### 与 3.3.1 的关联

**CLI 优先判断逻辑：**
- `scrapling extract get` → 仅静态页面
- `scrapling extract fetch` → **动态页面首选**（有 JS 执行）
- `scrapling extract stealthy-fetch` → **反爬动态页面**（有 JS 执行 + Cloudflare 绕过）
- Python API `StealthyFetcher.fetch(wait_selector=...)` → 需要等特定 CSS 选择器时才用（更精细控制）
- Python API `StealthySession(disable_resources=False, timeout=90000)` → 重度 SPA 单品页（JS 完全靠 XHR 加载）

**决策树：**
```
目标页面是静态的吗？
  ├─ 是 → scrapling extract get
  └─ 否 → 有 Cloudflare/反爬吗？
            ├─ 是 → scrapling extract stealthy-fetch
            └─ 否 → scrapling extract fetch
                    ↓ (如果内容不完整)
                    Python API (StealthyFetcher / StealthySession)
                    ↓ (如果仍然失败)
                    Level 3: browser 工具
```


### 3.7 Scrapling + iHerb 踩坑指南（Lessons Learned，2026-04-15 ~ 2026-04-30 实测）

**3.7.1 `css()` 返回的是 `Selectors` 集合，不是单个元素**

`page.css('.product-name')` 返回 `Selectors` 对象（类似列表），**不能直接调 `.get_all_text()`**。必须先索引或取第一个元素：

```python
# ❌ 错误
name = item.css('h2 a').get_all_text()  # AttributeError: 'Selectors' object has no attribute 'get_all_text'

# ✅ 正确：先索引
els = item.css('h2 a')
name = els[0].get_all_text().strip() if els else 'N/A'

# ✅ 正确：用 css_first（如果版本支持）
name_el = item.css_first('h2 a')
name = name_el.get_all_text().strip() if name_el else 'N/A'
```

**3.7.2 iHerb 搜索/品类页完整选择器指南（2026-04-30 实测验证）**

iHerb 搜索页和品类页（如 `/c/anti-aging-longevity`）的产品数据**大部分在 `a.absolute-link.product-link` 的 data 属性中**，不在可见文本里。

#### 完整字段提取方式（已验证可用）

```python
cell = page.css('.product-cell-container')[i]
a = cell.css('a.absolute-link.product-link')[0]

# ✅ 从 <a> 的 data 属性提取（最可靠）
name       = a.attrib.get('title', 'unknown')              # 产品全名
brand      = a.attrib.get('data-ga-brand-name', 'unknown')  # 品牌
href       = a.attrib.get('href', '')                       # 完整 URL
sku        = a.attrib.get('data-part-number', 'unknown')    # SKU
out_of_stock = a.attrib.get('data-ga-is-out-of-stock', '')  # "True"/"False"

# ✅ 价格：用 span.price bdi 取第一个 bdi（只有当前售价，无折扣/原价噪音）
price_bdi = cell.css('span.price bdi')
price = price_bdi[0].get_all_text(strip=True) if price_bdi else 'unknown'
# 输出示例: "¥113.74"

# ❌ 不要用 .product-price 的 get_all_text — 会包含原价+折扣百分比
# 例如: "¥113.74\n¥133.81\n15% off" 或 "¥140.26 ¥233.76 40% off"
# 更不要用它 — 缺货产品会混入 "Out of stock - We'll notify you! Notify me"

# ✅ 评分+评论数：从 .stars.scroll-to 的 title 属性提取（一个字段搞定）
stars_link = cell.css('.stars.scroll-to')
heat = stars_link[0].attrib.get('title', 'unknown') if stars_link else 'unknown'
# 输出示例: "4.7/5 - 315,858 Reviews"
```

#### 页面上没有的字段 → 直接填 unknown

搜索/品类页**不包含**以下信息，不要推断：
- `dosage_form`（剂型）— 不要从产品名猜测
- `pack_size`（规格）— 产品名里可能有但不是独立字段
- `core_ingredients`（核心成分）— 需要单品页，有则原样提取
- `core_selling_points`（卖点）— 需要单品页
- `claim_direction`（功效方向）— 不要硬编码

**不要试图从 `h2`、`.product-name` 等选择器取可见文本——它们是空的。**

**3.7.2.1 用品类页而非关键词搜索（2026-04-30 验证）**

iHerb 有完整的品类页体系（如 `/c/anti-aging-longevity`），一页返回 48 个产品，数据完整且排序反映真实市场热度。

```python
# ✅ 正确：直接用品类页 URL，让 iHerb 的排序告诉你市场格局
urls = ['https://cn.iherb.com/c/anti-aging-longevity']

# ❌ 错误：用 LLM 知识列出成分关键词逐个搜索
keywords = ["NMN", "resveratrol", "CoQ10", ...]  # knowledge-backed!
```

**为什么品类页优于关键词搜索：**
- 品类页的产品排序反映 iHerb 的销量/热度算法，是真实市场信号
- 关键词搜索结果不精确（如搜 "NAD+" 返回 NAC 产品）
- 关键词列表本身就是 knowledge-backed research（违反规则 3）
- 一次请求拿 48 个产品，比 15 个关键词各搜一次高效得多

**3.7.3 iHerb 单品页 URL 的 ID 可能已变更，会 301 重定向到完全不同的产品**

iHerb 搜索页返回的 `/pr/ID` 链接可能已经过期，访问时会 301 重定向到另一个完全不同的产品。例如 ID `136179` 原本是儿童专注力产品，跳转后变成了加湿器。

**实测情况（2026-04-22 运动饮料调研）：**
- 抓取 BCAA、creatine、electrolyte 等品类时，大量单品页返回 404
- 部分 URL 虽然 200 但内容完全不是预期产品
- 这是因为 iHerb 频繁更换产品 ID 或下架产品

**应对策略：**
- 单品页抓取后，用 `page.status` 检查是否为 200（301/307/410 说明有问题）
- 验证返回页面的产品名称是否与预期一致
- **如果单品页批量失败（>30% 404），果断退回到搜索页数据做分析**，不要反复重试同一批 URL
- 搜索页的 `data-ga-*` 属性数据通常比单品页更稳定
- **建议在采集时跳过单品页，直接用搜索页数据**，除非调研明确要求成分表

**3.7.4 搜索页 vs 单品页的数据质量判断**

| 数据维度 | 搜索页（`.product-cell-container`） | 单品页（`/pr/ID`） |
|---------|-----------------------------------|-------------------|
| 产品名称 | ✅ `title` 属性完整 | ✅ `h1` 完整 |
| 品牌 | ✅ `data-ga-brand-name` | ⚠️ 可能在不同位置 |
| 价格 | ✅ `.product-price` 文本 | ✅ 但可能有折扣标签 |
| 评论数 | ⚠️ 需要探索选择器 | ✅ `.reviews-count` |
| 成分详情 | ❌ 没有 | ✅ `Supplement Facts` |
| 稳定性 | ✅ 高 | ⚠️ ID 可能重定向 |
| 采集速度 | ✅ 快（一页 48 个） | ❌ 慢（每页 1 个） |

**建议：** 搜索页做广度采集（批量获取产品列表），单品页做深度验证（抽样验证成分和规格）。如果单品页大量重定向，以搜索页数据为准。

### 3.7.5 单品页成分表提取完整方案（2026-04-22 实测验证）

**核心发现：** iHerb 单品页的产品数据（Supplement Facts、成分表、价格等）**完全靠 XHR/API 动态加载**，`str(page)` 返回空壳，`page.text` 返回 TextHandler，必须用 `page.body.decode('utf-8')` 获取完整 HTML。

#### 完整可用的代码模板

```python
from scrapling.fetchers import StealthySession
import json, re

urls = [
    "https://cn.iherb.com/pr/life-extension-bioactive-complete-b-complex-60-vegetarian-capsules/67051",
    # ... 更多单品页
]

with StealthySession(
    headless=True,
    disable_resources=False,  # ⚠️ 必须 False！True 会导致 JS 依赖缺失
    timeout=90000,            # 至少 90 秒
) as session:
    for url in urls:
        page = session.fetch(url)

        if page.status != 200:
            print(f"⚠️ {url} -> status {page.status}")
            continue

        # ✅ 正确获取 HTML：用 page.body
        html = page.body.decode('utf-8', errors='replace')

        if len(html) < 5000:
            print(f"⚠️ {url} 内容太少，可能未完全加载")
            continue

        # 提取成分表（方法1：CSS table 选择器）
        for t in page.css('table'):
            text = t.get_all_text(strip=True)
            if 'Supplement' in text or 'supplement' in text or '成分' in text:
                print(f"Supplement Facts: {text}")
                break

        # 提取成分表（方法2：正则从 HTML 中提取）
        supplement_match = re.search(
            r'(?:Supplement Facts|营养成分)[^<]*</table>', html, re.DOTALL
        )
        if supplement_match:
            print(f"Raw HTML: {supplement_match.group(0)[:500]}")
```

#### 关键踩坑记录

| 错误做法 | 原因 | 正确做法 |
|---------|------|---------|
| `str(page)` | 返回 `<200 URL>`，不是 HTML | `page.body.decode('utf-8')` |
| `page.text` | 返回 TextHandler，可能显示为 None | `page.body.decode('utf-8')` |
| `disable_resources=True` | 砍掉 JS/CSS 依赖，页面加载不完整 | `disable_resources=False` |
| `timeout=45000` | iHerb 单品页首次加载 60-200s | `timeout=90000` 或更高 |
| 一次性爬所有单品页 | 首几页极慢（~200s/page） | Session 复用 + 缓存，后续页面快 5-10 倍 |
| 用 CLI `stealthy-fetch` | 不执行 JS，只能拿到空壳 | Python API `StealthySession` |

#### Session 复用提速数据（实测 5 页）

| 页面 | `disable_resources=True` | `disable_resources=False` |
|------|--------------------------|---------------------------|
| 1. supplements | 78.8s | 78.8s |
| 2. beauty | 77.7s | 76.7s |
| 3. sports | 76.9s | 102.3s（偶尔卡） |
| 4. grocery | 77.9s | **69.0s** |
| 5. topsellers | 80.3s | **7.6s** 🚀 |

**结论：** `disable_resources=False` 启用 disk cache 后，后续页面可提速 5-10 倍。首几页慢是固定成本。

#### 成分表输出示例（实测 Life Extension B-Complex）

```
Supplement facts
Serving Size: 2 Vegetarian Capsules
Servings Per Container: 30
Amount Per Serving:
% Daily Value
Thiamine (vitamin B1) (as thiamine HCl)          100 mg    8333%
Riboflavin (vitamin B2) (as riboflavin...)        75 mg    5769%
Niacin (as niacinamide and niacin)               100 mg     625%
Vitamin B6 (as pyridoxine HCl...)                100 mg    5882%
Folate (as L-5-methyltetrahydrofolate...)        680 mcg    170%
Vitamin B12 (as methylcobalamin)                 300 mcg   12500%
Biotin                                          1000 mcg    3333%
Pantothenic acid (as D-calcium pantothenate)     500 mg   10000%
```

### 3.7.6 iHerb 两阶段采集方案（2026-04-30 实测验证，字段覆盖率 100%）

搜索/品类页只能拿到 ~50% 的字段（名称、品牌、价格、评分）。要获取成分表、产品描述、规格等深度数据，必须**品类页广度 + 单品页深度**两步走。

#### 核心发现：单品页的 JSON-LD 是最佳数据源

iHerb 单品页内嵌 `<script type="application/ld+json">` 包含完整的 `schema.org/Product` 结构化数据，比 CSS 选择器提取更稳定、更完整：

```python
# JSON-LD 包含的字段（实测 5/5 产品均有）：
{
  "name": "产品全名",
  "brand": {"name": "品牌名"},
  "mpn": "SKU",
  "gtin12": "条形码",
  "category": {"name": "Supplements"},
  "weight": {"value": "0.49", "unitText": "kg"},
  "description": "完整产品描述（含卖点、功效声明、成分说明）",
  "aggregateRating": {"ratingValue": 4.7, "reviewCount": 315858},
  "offers": {"priceSpecification": [{"price": "113.74", "priceCurrency": "CNY"}]},
  "image": "产品图片 URL"
}
```

#### 两阶段代码模板

```python
import json, re
from scrapling import StealthyFetcher
from scrapling.fetchers import StealthySession

# ── Phase 1: 品类页广度采集 ──
fetcher = StealthyFetcher()
page = fetcher.fetch(
    'https://cn.iherb.com/c/anti-aging-longevity',  # 品类页，不是关键词搜索
    timeout=60000,
    wait_selector='.product-cell-container',
    wait_selector_state='attached',
    solve_cloudflare=True,
)
cells = page.css('.product-cell-container')  # 48 个产品

products = []
for cell in cells:
    a = cell.css('a.absolute-link.product-link')[0]
    price_bdi = cell.css('span.price bdi')
    stars_link = cell.css('.stars.scroll-to')
    products.append({
        "product_name": a.attrib.get('title', 'unknown'),
        "brand": a.attrib.get('data-ga-brand-name', 'unknown'),
        "product_url": a.attrib.get('href', ''),
        "sku": a.attrib.get('data-part-number', 'unknown'),
        "price": price_bdi[0].get_all_text(strip=True) if price_bdi else 'unknown',
        "out_of_stock": a.attrib.get('data-ga-is-out-of-stock', 'unknown'),
        "public_heat_signal": stars_link[0].attrib.get('title', 'unknown') if stars_link else 'unknown',
    })

# ── Phase 2: 单品页深度采集（JSON-LD） ──
with StealthySession(headless=True, disable_resources=False, timeout=90000) as session:
    for p in products:
        page = session.fetch(p['product_url'])
        html = page.body.decode('utf-8', errors='replace')

        # JSON-LD 提取
        for m in re.finditer(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL):
            try:
                data = json.loads(m.group(1))
                if isinstance(data, dict) and data.get('@type') == 'Product':
                    p['description'] = data.get('description', 'unknown')
                    p['gtin'] = data.get('gtin12', 'unknown')
                    p['category'] = data.get('category', {}).get('name', 'unknown')
                    w = data.get('weight', {})
                    p['weight'] = f"{w.get('value', '')} {w.get('unitText', '')}" if w else 'unknown'
                    break
            except (json.JSONDecodeError, KeyError):
                pass

        # Supplement Facts 表格
        for t in page.css('table'):
            text = t.get_all_text(strip=True)
            if any(kw in text.lower() for kw in ['supplement', 'serving', 'amount per']):
                p['supplement_facts'] = text
                break
```

#### 性能数据（实测 5 个产品）

| 阶段 | 耗时 | 说明 |
|------|------|------|
| Phase 1（品类页） | ~35s | 含 Cloudflare 绕过 |
| Phase 2 首个单品页 | ~40s | 冷启动 |
| Phase 2 后续单品页 | ~5s/个 | Session 复用 + disk cache |
| 5 个产品总计 | ~95s | Phase 1 + Phase 2 |

#### 字段覆盖率（实测 5/5 产品）

| 字段 | 来源 | 覆盖率 |
|------|------|--------|
| product_name | Phase 1 `a[title]` | 5/5 |
| brand | Phase 1 `a[data-ga-brand-name]` | 5/5 |
| price | Phase 1 `span.price bdi` | 5/5 |
| sku | Phase 1 `a[data-part-number]` | 5/5 |
| out_of_stock | Phase 1 `a[data-ga-is-out-of-stock]` | 5/5 |
| public_heat_signal | Phase 1 `.stars.scroll-to[title]` | 5/5 |
| product_url | Phase 1 `a[href]` | 5/5 |
| description | Phase 2 JSON-LD `description` | 5/5 |
| supplement_facts | Phase 2 CSS `table` | 5/5 |
| category | Phase 2 JSON-LD `category.name` | 5/5 |
| weight | Phase 2 JSON-LD `weight` | 5/5 |
| gtin | Phase 2 JSON-LD `gtin12` | 5/5 |

**注意：** `dosage_form`、`core_selling_points`、`core_ingredients`、`claim_direction`、`target_population` 这些字段在页面上没有独立的结构化数据，它们的信息散布在 `description` 和 `supplement_facts` 中。**不要用代码推断这些字段（规则 4），`core_ingredients` 直接原样提取 Supplement Facts 文本即可，不做格式化解析。**

### 3.8 子 Agent 结果提交规范（强制）

**核心原则：子Agent每采集到一条产品记录就立即 POST 到后端。前端实时展示已采集的数据。采集完成后提交元数据（研究范围、结论等），后端合并生成最终报告。子Agent不管理任何本地文件。**

#### 3.8.1 逐条推送记录（采集过程中）

每抓到一个产品，立即 POST 到后端：

```python
import json, requests

BACKEND = 'http://127.0.0.1:5001'

record = {
    "product_name": "星飞帆卓睿",
    "brand": "飞鹤",
    "source_platform": "品牌官网",
    "product_url": "https://...",
    "source_html_path": "/tmp/feihe_product.html",  # ⚠️ 必填！爬取到的 HTML 文件路径
    "dosage_form": "奶粉",
    "pack_size": "900g",
    "price": "¥388",
    "core_selling_points": "十五大活性脑营养、5大脑磷脂",  # ⚠️ 字符串，不是 list！
    "core_ingredients": "DHA 70mg, ARA 40mg, OPO 3.5g",   # 原样提取，不格式化
    "claim_direction": "促进大脑发育、增强免疫力",
    "public_heat_signal": "月销 5000+",
    "target_population": "0-3岁婴幼儿"
}

r = requests.post(
    f'{BACKEND}/api/subagent/record/{cid}',
    json={'record': record},
    timeout=10
)
print(f"✅ 已推送第 {r.json().get('count', '?')} 条记录")
```

**每条 record 必须包含的字段（参考 output-schemas.md）：**
`product_name`, `brand`, `source_platform`, `product_url`, **`source_html_path`**, `dosage_form`, `pack_size`, `price`, `core_selling_points`, `core_ingredients`, `claim_direction`, `public_heat_signal`, `target_population`

**⚠️ `source_html_path` 强制规则（后端会校验，缺失或无效直接拒绝）：**

1. **必填** — 没有 `source_html_path` 的记录会被后端拒绝（`400 Missing source_html_path`）
2. **文件必须存在** — 路径指向的 HTML 文件必须是你用 scrapling/web_fetch 实际爬取并保存到磁盘的文件
3. **文件不能太小** — < 2KB 的文件会被拒绝（Cloudflare 拦截页/空壳通常 < 2KB）
4. **产品名必须出现在 HTML 中** — 后端会检查 `product_name` 的关键词是否出现在 HTML 文件内容中，不匹配则拒绝
5. **同一个 HTML 文件可以对应多条记录** — 如果一个搜索页包含多个产品，多条记录可以共用同一个 `source_html_path`

**正确工作流：** 先用 scrapling 爬取页面 → 保存 HTML 到 `/tmp/xxx.html` → 从 HTML 中提取数据 → 提交记录时带上 `source_html_path`

**❌ 如果你没有爬到 HTML 文件，就不能提交记录。没有来源文件 = 没有数据。**

⚠️ **字段值类型强制规则：**

**所有字段值必须是基本类型（字符串、数字），绝对不能是 Python list / dict！** 多个值用 `、`（中文顿号）或 `, ` 连接成字符串。

**⚠️ 提交前自动过滤（后端强制，提交了也会被拒）：**

后端会自动拒绝以下两类低质量记录，**子Agent应在提交前自行跳过，避免浪费请求**：

1. **unknown 字段过多** — 10 个内容字段（`product_name`, `brand`, `dosage_form`, `pack_size`, `price`, `core_selling_points`, `core_ingredients`, `claim_direction`, `public_heat_signal`, `target_population`）中有 **≥7 个**为 `unknown` / 空 / 缺失时，后端直接拒绝。搜索页只能提取名称+品牌+价格+评分的记录，其余全是 unknown，**不要提交**——先爬单品页补全数据，或直接跳过该产品。
2. **详情页链接无效** — `product_url` 为空、`unknown`、`N/A` 或其他占位值时，后端直接拒绝。每条记录必须有可访问的产品详情页 URL。

```python
# ✅ 提交前检查：unknown 过多就跳过
_content_fields = ['product_name','brand','dosage_form','pack_size','price',
                   'core_selling_points','core_ingredients','claim_direction',
                   'public_heat_signal','target_population']
unknown_cnt = sum(1 for f in _content_fields if record.get(f) in ['unknown','',None])
if unknown_cnt >= 7:
    print(f"⏭️ 跳过 {record.get('product_name','?')}：{unknown_cnt}/10 字段为 unknown")
    continue

# ✅ 提交前检查：product_url 无效就跳过
if not record.get('product_url') or record['product_url'] in ['unknown','N/A','none','null']:
    print(f"⏭️ 跳过 {record.get('product_name','?')}：product_url 无效")
    continue
```

**推送节奏：** 每采集到一条就推一条，不要攒批。这样即使子Agent中途超时，已推送的记录不会丢失（后端已落盘），前端也能实时看到进度。

**⚠️ 提交方式约束（配合规则 5）：**

提交记录的代码**必须**是从 HTML 文件中程序化提取数据后直接 POST，**禁止**先把产品数据硬编码到 `products = [...]` 列表中再循环提交。

```python
# ❌ 禁止：硬编码列表 → 循环提交
products = [{"product_name": "xxx", "price": "xxx", ...}, ...]  # 手写的！
for p in products:
    requests.post(API, json={"record": p})

# ✅ 正确：解析 HTML → 逐条提取 → 逐条提交
page = Selector(open(html_path).read())
for cell in page.css('.product-cell-container'):
    record = extract_from_cell(cell)  # 从 HTML 元素提取
    record["source_html_path"] = html_path
    requests.post(API, json={"record": record})
```

#### 3.8.2 断点续传

逐条推送天然支持断点续传：
- 已推送的记录已在后端落盘（`tasks/{cid}_records.json`）
- 子Agent中途超时后，下次重新运行同一个 cid 时，可以先查询已有记录数量，跳过已采集的部分
- 用户在前端点"重置"会清空已有记录，从头开始

```python
# 查询已有记录数量
r = requests.get(f'{BACKEND}/api/conversation/{cid}/records?offset=0', timeout=10)
existing = r.json().get('total', 0)
print(f"🔄 已有 {existing} 条记录，从第 {existing+1} 条继续")
```

### 4. Standardize the findings

Convert raw findings into the schema for the chosen module. Use the exact field groups from [references/output-schemas.md](references/output-schemas.md). Keep terminology stable across records so downstream aggregation stays usable.

### 5. Produce a decision-ready output

Every final answer must contain:

- A short scope statement
- The structured result table or record set
- A compact synthesis section
- Clear uncertainty notes

For formula recommendation tasks, the final answer must also state why each ingredient was selected and whether the support is clinical, mechanistic, or market-driven.

## Hard Rules

- Prioritize human clinical evidence over animal, in vitro, review, or marketing claims.
- Separate observed facts from inferred judgments.
- When inferring positioning, formulation logic, or commercialization path, label it as an inference.
- Do not fabricate unavailable dosage, sales, review, or efficacy data.
- Do not output vague summaries when the request clearly requires a structured table.
- Keep the workflow modular: one primary task, then only the minimum supporting tasks needed.
- **Do not waste time on repeatedly blocked sources.** If web_fetch + scrapling + browser all fail on a platform, mark the data as unknown and document the gap. Do not fall back to knowledge-based generation or search aggregation pages (see 规则 3).
- **采集数量：质量优先，零容忍造假。** 最低要求是 0 条 — 如果所有平台都被拦截，0 条真实记录 + 完整的失败报告，远好于 30 条假记录。每条记录必须有可追溯的 `source_html_path`。采集失败时在「不确定性与缺口」中列出尝试过的 URL 和失败原因，建议用户调整采集范围，**绝对不要用 LLM 知识凑数**。

## Output Discipline

- Prefer Markdown tables for concise outputs and CSV-style field ordering when data is dense.
- Use Chinese when the user writes in Chinese, unless a source field requires original English naming.
- Keep ingredient names in both Chinese and English when available.
- For literature tasks, always include the source link.
- For recommendation tasks, produce 2-3 options only when the user explicitly asks for multiple方案 or the task is comparative by nature.

## When To Read Extra References

- Read [references/task-routing.md](references/task-routing.md) when the user intent is ambiguous or spans multiple modules.
- Read [references/output-schemas.md](references/output-schemas.md) before producing the final structured output.

## Scraping Examples

Before writing scraping scripts, read the example scripts in `examples/` for reference:

- [examples/iherb_scrape_phase1.py](examples/iherb_scrape_phase1.py) — Phase 1: scrape category pages to collect product list (name, brand, price, URL, heat signal).
- [examples/iherb_scrape_phase2.py](examples/iherb_scrape_phase2.py) — Phase 2: scrape detail pages with `StealthySession`, extract JSON-LD and Supplement Facts, then POST records to the local API.

Key patterns demonstrated:
- Use `scrapling.StealthyFetcher` for single pages, `scrapling.fetchers.StealthySession` for multi-page sessions.
- Use `requests` or `urllib.request` to POST records to the backend API.
- Filter products by relevance before scraping detail pages.
- Extract structured data from JSON-LD `<script>` tags and HTML tables.
- Skip records with too many unknown fields (≥7/10).
