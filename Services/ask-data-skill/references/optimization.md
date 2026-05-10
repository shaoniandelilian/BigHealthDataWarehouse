# SQL 性能优化规则

生成 SQL 时自动应用以下优化规则。核心目标：**在确保最终输出结果与原始语义完全一致的前提下，优化执行性能。**

## 规则 1：谓词下推 — 过滤条件尽早执行

```sql
-- ❌ 先 JOIN 再过滤
SELECT * FROM user_events a
JOIN user_profiles b ON a.user_id = b.user_id
WHERE a.dt = '2026-03-12';

-- ✅ 先过滤再 JOIN
SELECT a.*, b.*
FROM (SELECT * FROM user_events WHERE dt = '2026-03-12') a
JOIN user_profiles b ON a.user_id = b.user_id;
```

收益：缩小参与 JOIN 的数据规模，降低 Shuffle 开销。

## 规则 2：CTE 复用 — 避免重复子查询

```sql
-- ❌ 同一子查询扫描两次
SELECT * FROM (SELECT * FROM user_events WHERE dt = '2026-03-12') a WHERE event = 'click'
UNION ALL
SELECT * FROM (SELECT * FROM user_events WHERE dt = '2026-03-12') b WHERE event = 'buy';

-- ✅ CTE 复用
WITH base AS (
  SELECT * FROM user_events WHERE dt = '2026-03-12'
)
SELECT * FROM base WHERE event = 'click'
UNION ALL
SELECT * FROM base WHERE event = 'buy';
```

## 规则 3：分区剪枝 — 过滤条件必须命中分区字段

```sql
-- ❌ 对分区字段做函数转换，分区剪枝失效
SELECT * FROM user_logs WHERE DATE_FORMAT(dt, 'yyyy-MM') = '2026-03';

-- ✅ 直接对分区字段过滤
SELECT * FROM user_logs WHERE dt >= '20260301' AND dt < '20260401';
```

**禁止**对分区字段做 CAST、DATE_FORMAT、SUBSTR 等函数处理。

## 规则 4：广播小表（MAPJOIN）

```sql
-- ✅ 小表加 MAPJOIN Hint
SELECT /*+ MAPJOIN(dim) */ a.user_id, a.event, b.category
FROM user_events a
JOIN dim_category b ON a.category_id = b.category_id;
```

判断依据：维度表、字典表、配置表等，行数 < 100 万或体积 < 50MB 时使用。

## 规则 5：避免笛卡尔积

```sql
-- ❌ 缺少 JOIN 条件
SELECT a.*, b.* FROM table_a a, table_b b WHERE a.dt = '2026-03-12';

-- ✅ 补全 JOIN 条件
SELECT a.*, b.*
FROM table_a a
JOIN table_b b ON a.user_id = b.user_id
WHERE a.dt = '2026-03-12';
```

## 规则 6：Group By 数据倾斜 — 三步加盐聚合

**适用**：SUM、COUNT(*)、MAX、MIN。AVG 需改写为 `SUM/COUNT`。
**不适用**：`COUNT(DISTINCT ...)`（加盐会导致重复计数）。

```sql
-- ❌ 直接 GROUP BY，热点 key 拖慢任务
SELECT user_id, COUNT(*) AS order_cnt, SUM(amount) AS total_amount
FROM orders WHERE status = 'paid'
GROUP BY user_id;

-- ✅ 三步加盐聚合
WITH salted AS (
  SELECT user_id, amount,
         CAST(FLOOR(RAND() * 40) AS INT) AS salt
  FROM orders WHERE status = 'paid'
),
stage1 AS (
  SELECT user_id, salt,
         COUNT(*) AS partial_cnt,
         SUM(amount) AS partial_sum
  FROM salted
  GROUP BY user_id, salt
)
SELECT user_id,
       SUM(partial_cnt) AS order_cnt,
       SUM(partial_sum) AS total_amount
FROM stage1
GROUP BY user_id;
```

注意事项：
- **不要**在同一层 SELECT 和 GROUP BY 中分别写两次 `RAND()`，先在 CTE 中固化 salt
- AVG 改写：`SUM(partial_sum) / SUM(partial_cnt)`，不能写 `AVG(partial_avg)`
- 盐值从 8、16、32 开始尝试，根据倾斜程度调整

## 自动应用策略

| 规则 | 应用时机 |
|------|---------|
| 谓词下推 | 所有含 JOIN 的查询自动应用 |
| 分区剪枝 | 所有查询自动应用（必须指定分区） |
| CTE 复用 | 检测到重复子查询时自动应用 |
| MAPJOIN | 识别到维度表/字典表关联时自动应用 |
| 避免笛卡尔积 | 生成 SQL 时自动检查 JOIN 条件完整性 |
| 加盐聚合 | 用户明确要求优化或检测到明显倾斜风险时应用 |
