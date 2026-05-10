# 示例 1：基础查询

## 场景 A：指定字段 + 条件筛选（增量表）

**用户输入**：查询供应链全流程明细表中承诺类型为次日达且最晚出库时间大于2026-03-13的spu和P码

**思考过程**：
1. "供应链全流程明细表" → 匹配表 COMMENT "dwm-供应链域-全流程明细表-增量表" → `zz.dwm_scm_detail_di`
2. 表名以 `_di` 结尾 → 增量表，需指定分区
3. "承诺类型为次日达" → 字段 COMMENT "承诺类型:0:普通，1：次日达" → `promise_type_code = 1`
4. "最晚出库时间大于2026-03-13" → `outbound_latest_time >= '2026-03-13 00:00:00'`
5. "spu" → `spu_id`，"P码" → COMMENT "唯一码P码" → `unique_id`
6. 用户提到了具体日期 2026-03-13 → 分区 `pt = '20260313'`

**生成 SQL**：

```sql
SELECT
    spu_id    AS spu,
    unique_id AS P码
FROM zz.dwm_scm_detail_di
WHERE pt = '20260313'
  AND promise_type_code = 1
  AND outbound_latest_time >= '2026-03-13 00:00:00';
```

---

## 场景 B：全字段查询（全量表，未指定分区）

**用户输入**：查询供应链效率归因分析表全部数据

**思考过程**：
1. "供应链效率归因分析表" → 匹配 `zz.ads_scm_effect_attribution_analysis_target`
2. 表名无 `_di/_df` 等后缀 → 取最大分区
3. 用户未指定字段 → `SELECT *`

**执行步骤**：

```sql
-- Step 1: 获取最大分区
SELECT MAX(pt) FROM zz.ads_scm_effect_attribution_analysis_target;
-- 结果: 20260413
```

```sql
-- Step 2: 查询
SELECT *
FROM zz.ads_scm_effect_attribution_analysis_target
WHERE pt = '20260413';
```

---

## 场景 C：指定字段 + 中文别名（全量表，指定日期）

**用户输入**：查询供应链效率归因表中日期为20260312的商品一级类目的供应链入库量

**思考过程**：
1. 匹配表 `zz.ads_scm_effect_attribution_analysis_target`
2. "日期为20260312" → `date_id` 字段筛选，分区取 T+1 即 `pt = '20260313'`
3. "商品一级类目" → `level1_category_name`
4. "供应链入库量" → `scm_inbound_cnt_1d`

**生成 SQL**：

```sql
SELECT
    date_id              AS 日期,
    level1_category_name AS 商品一级类目,
    scm_inbound_cnt_1d   AS 供应链入库量
FROM zz.ads_scm_effect_attribution_analysis_target
WHERE pt = '20260313'
  AND date_id = '20260312';
```
