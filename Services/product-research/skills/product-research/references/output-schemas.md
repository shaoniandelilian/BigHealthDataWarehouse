# Output Schemas

Use these schemas to keep the output stable and machine-readable.

## Shared Response Frame

Every final answer should follow this order:

1. `研究范围`
2. `结构化结果`
3. `关键结论`
4. `不确定性与缺口`

## Schema: Market Research

### Record fields

| Field | Meaning |
| --- | --- |
| product_name | 产品名称 |
| brand | 品牌 |
| source_platform | 平台来源 |
| product_url | 产品链接 |
| dosage_form | 剂型 |
| pack_size | 规格 |
| price | 价格 |
| core_selling_points | 核心卖点 |
| core_ingredients | 核心原料。直接从页面原样提取 Supplement Facts 区域的文本内容，不做任何格式化、翻译或重组。如果无法获取则填 `unknown`。 |
| claim_direction | 宣传方向 |
| public_heat_signal | 销量、评论数或热度 |
| target_population | 适用人群 |

### Aggregation fields

| Field | Meaning |
| --- | --- |
| total_product_count | 市面产品总量 |
| top_ingredients | 高频原料 Top10 |
| top_dosage_forms | 高频剂型 Top5 |
| top_selling_points | 高频卖点 Top10 |
| price_band_distribution | 价格带分布 |
| hot_selling_products | 热销产品清单 |
| platform_differences | 平台趋势差异 |

## Schema: Clinical Ingredient Review

| Field | Meaning |
| --- | --- |
| ingredient_name_cn | 原料中文名 |
| ingredient_name_en | 原料英文名 |
| ingredient_class | 原料类别 |
| benefit_direction | 功效方向 |
| mechanism | 作用机制 |
| human_clinical_dose | 人体临床剂量 |
| intervention_duration | 干预周期 |
| study_population | 受试人群 |
| key_finding | 关键结论 |
| evidence_type | RCT / Meta / Review / Animal / In vitro |
| source_url | 原文链接 |
| development_fit | 是否适合继续开发 |

## Schema: Competitor Formula Teardown

| Field | Meaning |
| --- | --- |
| product_positioning | 产品定位 |
| target_population | 目标人群 |
| core_selling_points | 核心卖点 |
| formula_composition | 配方组成 |
| ingredient_categories | 原料分类 |
| public_dose_info | 剂量信息 |
| market_concept | 市场概念 |
| scientific_logic | 科研逻辑 |
| marketing_led_judgment | 是否偏营销概念 |
| clinical_support_judgment | 是否有临床支撑 |
| channel_fit | 国内还是跨境路径 |
| formula_type | 基础营养型或功能复配型 |
| functional_layout | 激素平衡、睡眠、骨骼、皮肤、情绪、代谢等布局 |
| symbolic_addition_risk | 是否存在象征性添加 |
| replication_value | 是否具备复现价值 |

Fields ending with `judgment`, `risk`, or `value` must be labeled as inference when they are not directly supported by a cited source.

## Schema: Formula Recommendation

| Field | Meaning |
| --- | --- |
| formula_name | 方案名 |
| target_user | 目标人群 |
| benefit_direction | 功效方向 |
| ingredient | 原料 |
| suggested_dose | 建议剂量 |
| selection_reason | 选择理由 |
| dose_rationale | 剂量依据来源 |
| market_concept | 市场概念建议 |
| dosage_form | 适合剂型 |
| regulatory_note | 初步法规风险提示 |

## Writing Rules

- Use original source naming for product titles and ingredient English names when possible.
- Do not merge multiple source links into one synthetic citation field when per-record links are available.
- If a field is unavailable, use `unknown` or `not publicly available`.
- If a judgment is inferred, prefix with `Inference:`.
