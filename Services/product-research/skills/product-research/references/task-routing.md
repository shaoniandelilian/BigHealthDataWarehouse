# Task Routing

Use this file to decide which module the request belongs to and what evidence is required.

## Primary Modules

### 1. `market_research`

Use when the user wants to understand what products exist in the market and how they are positioned.

Typical requests:

- 帮我看市面上的更年期产品有哪些
- 哪些 menopause supplement 卖得最好
- 更年期睡眠产品的主流卖点是什么

Core deliverable:

- A structured product list
- Frequency and trend aggregation
- A short market synthesis

Required output fields:

- Product name
- Brand
- Source platform
- Product link
- Dosage form
- Pack size
- Price
- Core selling points
- Core ingredients
- Claim direction
- Sales, review count, or heat if publicly available
- Target population

Required aggregation:

- Product count
- Top ingredients
- Top dosage forms
- Top selling points
- Price band distribution
- Hot-selling product list
- Platform differences

### 2. `clinical_ingredient_review`

Use when the user asks for ingredient evidence, mechanism, dosage, trial duration, or suitability for development.

Typical requests:

- 整理更年期常用原料的人体临床剂量和机制
- S-equol 对潮热有没有人体临床
- 更年期睡眠方向有哪些有证据的原料

Core deliverable:

- Ingredient evidence table with human evidence prioritized
- Short development assessment

Required output fields:

- Ingredient name in Chinese and English
- Ingredient class
- Benefit direction
- Mechanism
- Human clinical dosage
- Intervention duration
- Study population
- Key conclusion
- Evidence type
- Source link
- Development suitability

Evidence ranking:

1. Human clinical trial
2. Meta-analysis or systematic review
3. Narrative review
4. Animal study
5. In vitro study

Do not merge these evidence levels into one conclusion without labeling the level.

### 3. `competitor_formula_teardown`

Use when the request is about a specific product or brand and the goal is to reconstruct formulation logic.

Typical requests:

- 帮我拆某品牌更年期产品
- 这个商品链接背后的配方逻辑是什么
- 这个产品更偏科研还是营销

Core deliverable:

- Product positioning reconstruction
- Formula composition breakdown
- Commercialization and evidence judgment

Required output fields:

- Product positioning
- Target population
- Core selling points
- Formula composition
- Ingredient categories
- Dosage information if public
- Market concept
- Scientific logic
- Whether the concept is marketing-led
- Whether clinical support exists
- Domestic or cross-border fit

Required judgments:

- Basic nutrition vs functional compound formula
- Main functional directions
- Symbolic addition risk
- Replication value

### 4. `formula_recommendation`

Use when the user wants a proposed formula or a revised version of a competitor idea.

Typical requests:

- 做一个更年期女性综合营养产品
- 做更年期睡眠方向产品
- 复现竞品并优化

Core deliverable:

- A formula proposal anchored in evidence and product strategy

Required output fields:

- Recommended ingredient combination
- Reason for each ingredient
- Suggested dosage
- Dosage evidence source
- Benefit direction
- Market concept suggestion
- Dosage-form suggestion
- Preliminary regulatory risk note

Only produce multiple proposals when the user asks for alternatives or when the task itself requires comparison.

## Module Combination Rules

Use the minimum necessary combination:

- `formula_recommendation` may pull from `clinical_ingredient_review`
- `formula_recommendation` may pull selected signals from `market_research`
- `competitor_formula_teardown` may pull selected evidence from `clinical_ingredient_review`
- `market_research` should stay independent unless the user explicitly asks for interpretation beyond market facts

## Evidence Boundaries

- Public page facts are facts only for what the page shows
- Mechanism and efficacy need scientific evidence
- Commercial judgments such as "营销导向" or "复现价值" are inferences and must be labeled as such
