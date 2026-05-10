# 示例 3：聚合与开窗

## 场景 A：聚合 + GROUP BY

**用户输入**：查询供应链全流程明细表中最近30天的入库单量，维度是仓库名

**思考过程**：
1. 匹配表 `zz.dwm_scm_detail_di`（增量表）
2. "最近30天" → 先查最大分区确定基准日期，再计算30天范围
3. "入库单量" → `COUNT(inbound_id)`
4. "维度是仓库名" → `GROUP BY warhouse_name`

**执行步骤**：

```sql
-- Step 1: 获取最大分区
SELECT MAX(pt) FROM zz.dwm_scm_detail_di;
-- 结果: 20260413
```

```sql
-- Step 2: 聚合查询（最近30天 = 20260314 ~ 20260413）
SELECT
    warhouse_name          AS 仓库名,
    COUNT(inbound_id)      AS 最近30天入库单量
FROM zz.dwm_scm_detail_di
WHERE pt >= '20260314' AND pt <= '20260413'
GROUP BY warhouse_name;
```

---

## 场景 B：开窗函数 — ROW_NUMBER

**用户输入**：查询供应链全流程明细表中3月13日首个入库的spu

**思考过程**：
1. "首个入库" → `ROW_NUMBER() OVER(ORDER BY inbound_create_time ASC)` 取 `rn = 1`
2. "3月13日" → `pt = '20260313'`

**生成 SQL**：

```sql
SELECT spu
FROM (
    SELECT
        spu_id AS spu,
        ROW_NUMBER() OVER(ORDER BY inbound_create_time ASC) AS rn
    FROM zz.dwm_scm_detail_di
    WHERE pt = '20260313'
)
WHERE rn = 1;
```

---

## 场景 C：开窗函数 — LEAD

**用户输入**：查询3月13日每个仓库的入库记录，以及下一条入库的时间

**思考过程**：
1. "下一条入库的时间" → `LEAD(inbound_create_time) OVER(...)`
2. "每个仓库" → `PARTITION BY warhouse_name`

**生成 SQL**：

```sql
SELECT
    warhouse_name       AS 仓库名,
    inbound_id          AS 入库单ID,
    inbound_create_time AS 入库时间,
    next_inbound_time   AS 下一条入库时间
FROM (
    SELECT
        warhouse_name,
        inbound_id,
        inbound_create_time,
        LEAD(inbound_create_time) OVER(
            PARTITION BY warhouse_name
            ORDER BY inbound_create_time ASC
        ) AS next_inbound_time
    FROM zz.dwm_scm_detail_di
    WHERE pt = '20260313'
);
```
