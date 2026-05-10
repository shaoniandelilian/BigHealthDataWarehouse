# Text2SQL 核心转换规则

## 1. 表匹配规则

当用户用自然语言描述查询需求时，按以下优先级匹配目标表：

1. **表名英文匹配**：用户提问中出现的关键词与表名（英文）匹配
2. **表 COMMENT 匹配**：用户提问中的关键词与表的 COMMENT（中文描述）匹配
3. **字段 COMMENT 匹配**：统计用户提问关键词在各表字段 COMMENT 中的命中数量，命中最多的表优先

匹配公式：`coalesce(英文表名匹配, 中文COMMENT匹配, 字段COMMENT命中数)`

## 2. 字段匹配规则

用户提到的字段信息按以下优先级匹配：

1. **英文字段名**：用户提到的信息优先匹配表中英文字段名
2. **中文 COMMENT**：英文未匹配到时，匹配字段的中文 COMMENT
3. **未指定字段**：用户未明确要求字段时，默认 `SELECT *`

## 3. 查询字段展示

查询时**必须**将字段用中文 COMMENT 作为别名展示，方便业务人员阅读：

```sql
SELECT
    date_id           AS 日期,
    level1_category_name AS 商品一级类目,
    scm_inbound_cnt_1d   AS 供应链入库量
FROM table_name
WHERE ...
```

规则：
- 优先取字段的 COMMENT 作为别名
- 如果 COMMENT 为空，保留原字段名
- `SELECT *` 时不加别名

## 4. WHERE 条件生成

根据用户描述自动生成过滤条件：

- **时间范围**：识别用户提到的时间信息，转换为对应的时间字段过滤条件
- **字段筛选**：识别用户提到的筛选条件（优先匹配英文字段名），生成 WHERE 子句
- **枚举值匹配**：根据字段 COMMENT 中的枚举说明匹配用户描述的值

示例：用户说"承诺类型为次日达" → COMMENT 中 `承诺类型:0:普通，1：次日达，2：当日达` → `promise_type_code = 1`

## 5. 多表关联规则

当用户查询涉及多张表时：

1. **同名字段关联**：优先搜索两张表中的同名字段作为 JOIN 条件
2. **语义匹配关联**：无同名字段时，根据字段含义（COMMENT）选择最匹配的字段关联
3. **JOIN 类型选择**：
   - 用户要求"两边都匹配的" → `JOIN`（内连接）
   - 用户要求"某张表的全部信息" → `LEFT JOIN`
4. **谓词下推**：对分区表的过滤条件必须在子查询中先执行，再进行 JOIN

```sql
-- ✅ 正确：谓词下推
SELECT a.*, b.*
FROM (SELECT * FROM table_a WHERE pt = '20260313') a
JOIN (SELECT * FROM table_b WHERE pt = '20260313') b
  ON a.id = b.id;

-- ❌ 错误：先 JOIN 再过滤
SELECT a.*, b.*
FROM table_a a JOIN table_b b ON a.id = b.id
WHERE a.pt = '20260313';
```

## 6. 聚合计算识别

识别用户的聚合需求并生成对应 SQL：

| 用户表述 | SQL 函数 |
|---------|---------|
| "数量"、"多少条"、"单量" | `COUNT(field)` |
| "总量"、"合计"、"总和" | `SUM(field)` |
| "平均"、"均值" | `AVG(field)` → 优化为 `SUM(field)/COUNT(field)` |
| "最大"、"最高" | `MAX(field)` |
| "最小"、"最低" | `MIN(field)` |
| "去重数量"、"有多少个不同的" | `COUNT(DISTINCT field)` |

聚合时必须识别用户要求的维度字段，生成 `GROUP BY`。

## 7. 开窗函数识别

| 用户表述 | SQL 函数 |
|---------|---------|
| "第一个"、"排名第N"、"Top N" | `ROW_NUMBER() OVER(...)` |
| "上一个"、"前一条" | `LAG() OVER(...)` |
| "下一个"、"后一条" | `LEAD() OVER(...)` |
| "累计" | `SUM() OVER(... ROWS UNBOUNDED PRECEDING)` |

开窗查询通常需要嵌套子查询，外层再做过滤：

```sql
SELECT *
FROM (
    SELECT field, ROW_NUMBER() OVER(ORDER BY time_field ASC) AS rn
    FROM table_name
    WHERE pt = '20260313'
)
WHERE rn = 1;
```
