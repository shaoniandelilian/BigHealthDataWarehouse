# 分区策略规则

## 表命名与分区类型

| 表名后缀 | 类型 | 说明 |
|---------|------|------|
| `_di` | 日增量 | Daily Incremental |
| `_hi` | 小时增量 | Hourly Incremental |
| `_ri` | 实时增量 | Realtime Incremental |
| `_df` | 日全量 | Daily Full |
| `_hf` | 小时全量 | Hourly Full |

分区字段统一为 `pt`，格式为 `yyyyMMdd`（如 `20260313`）。

## 分区筛选规则

### 增量表（`_di` / `_hi` / `_ri`）

增量表每个分区只包含该时间段的新增/变更数据，因此：

- **用户指定时间范围**：根据时间范围生成分区条件

```sql
-- 用户：查询3月10日到3月13日的数据
SELECT ...
FROM zz.dwm_scm_detail_di
WHERE pt >= '20260310' AND pt <= '20260313'
```

- **用户指定单日**：直接指定对应分区

```sql
WHERE pt = '20260313'
```

- **用户说"最近N天"**：生成范围分区条件，需要先获取最大分区来确定基准日期

```sql
-- 先获取最大分区
SELECT MAX(pt) FROM zz.dwm_scm_detail_di;
-- 假设结果为 20260413，则最近30天
WHERE pt >= '20260314' AND pt <= '20260413'
```

### 全量表（`_df` / `_hf`）

全量表每个分区包含截至该时间点的全量数据，因此只需取一个分区：

- **用户指定日期**：取对应分区（T+1 逻辑，用户说的业务日期对应的分区）

```sql
-- 用户：查询3月12日的数据（全量表取 T+1 分区）
WHERE pt = '20260313'
```

- **用户未指定日期**：取最大分区

```sql
-- 先查最大分区
SELECT MAX(pt) FROM zz.ads_scm_effect_attribution_analysis_target;
-- 使用最大分区
WHERE pt = '<max_pt>'
```

### 无后缀表 / 无法识别后缀

统一取最大分区：

```sql
SELECT MAX(pt) FROM <table_name>;
```

## 多表关联时的分区处理

每张表的分区独立处理，各自按上述规则确定分区值：

```sql
SELECT a.*, b.*
FROM (
    SELECT * FROM zz.dwm_scm_detail_di
    WHERE pt >= '20260310' AND pt <= '20260313'
) a
JOIN (
    SELECT * FROM zz.ads_scm_effect_attribution_analysis_target
    WHERE pt = '20260313'  -- 全量表取最大分区或指定分区
) b
ON a.level1_category_name = b.level1_category_name;
```

## 关键原则

1. **任何查询都必须指定分区条件**，禁止全表扫描
2. 分区条件直接作用于 `pt` 字段，**不要对 pt 做函数转换**（会导致分区剪枝失效）
3. 不确定分区值时，**先查 `SELECT MAX(pt)` 再构造查询**
