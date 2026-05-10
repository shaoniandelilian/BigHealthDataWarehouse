# 示例 2：多表关联

## 场景 A：同名字段关联（内连接）

**用户输入**：查询明细表和效率归因表中两边都匹配的一级类目和入库量信息

**思考过程**：
1. 明细表 → `zz.dwm_scm_detail_di`（增量表），效率归因表 → `zz.ads_scm_effect_attribution_analysis_target`
2. 搜索同名字段：`level1_category_name`、`warhouse_name` 存在于两张表中
3. 选择语义最合适的关联字段：`level1_category_name`（一级类目）
4. "两边都匹配" → `JOIN`（内连接）
5. 谓词下推：各表分区条件在子查询中先过滤
6. 增量表需确定分区范围，全量表取最大分区

**生成 SQL**：

```sql
SELECT
    t0.level1_category_name AS 一级类目,
    t0.inbound_cnt          AS 入库数量,
    t1.scm_inbound_cnt_1d   AS 供应链入库量
FROM (
    SELECT level1_category_name, inbound_cnt
    FROM zz.dwm_scm_detail_di
    WHERE pt = '20260413'
) t0
JOIN (
    SELECT level1_category_name, scm_inbound_cnt_1d
    FROM zz.ads_scm_effect_attribution_analysis_target
    WHERE pt = '20260413'
) t1
ON t0.level1_category_name = t1.level1_category_name;
```

---

## 场景 B：左连接

**用户输入**：查询明细表中所有入库记录，关联效率归因表补充供应链入库量

**思考过程**：
1. "明细表中所有" → 以明细表为主 → `LEFT JOIN`
2. 关联字段：`level1_category_name`

**生成 SQL**：

```sql
SELECT
    t0.inbound_id            AS 入库单ID,
    t0.spu_name              AS spu名称,
    t0.level1_category_name  AS 一级类目,
    t1.scm_inbound_cnt_1d    AS 供应链入库量
FROM (
    SELECT inbound_id, spu_name, level1_category_name
    FROM zz.dwm_scm_detail_di
    WHERE pt = '20260413'
) t0
LEFT JOIN (
    SELECT level1_category_name, scm_inbound_cnt_1d
    FROM zz.ads_scm_effect_attribution_analysis_target
    WHERE pt = '20260413'
) t1
ON t0.level1_category_name = t1.level1_category_name;
```
