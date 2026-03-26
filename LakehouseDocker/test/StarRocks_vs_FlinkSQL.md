Table: paimon_order
Rows: 3413206 (21个cust_key，唯一的order_key)
Nodes: 1TaskManager, 1BE 都是单点计算
Schema:
```sql
CREATE TABLE paimon_order (
    `order_key` BIGINT,
    `cust_key` INT NOT NULL,
    `total_price` DECIMAL(15, 2),
    `order_date` DATE,
    `order_priority` STRING,
    `clerk` STRING,
    PRIMARY KEY (`order_key`) NOT ENFORCED
);
```

## 1. 按月份统计订单量、总金额、均价，并按金额倒序排序

- StarRocks
1 row in set (3.83 sec)
```sql
SELECT
  DATE_FORMAT(order_date, '%Y-%m') AS ym,
  COUNT(*) AS order_cnt,
  SUM(total_price) AS total_amount,
  AVG(total_price) AS avg_amount,
  MAX(total_price) AS max_amount,
  MIN(total_price) AS min_amount
FROM paimon_order
GROUP BY DATE_FORMAT(order_date, '%Y-%m')
ORDER BY total_amount DESC, order_cnt DESC;
```

- Flink
1 row in set (6.62 seconds)
```sql
SELECT
  DATE_FORMAT(CAST(order_date AS TIMESTAMP), '%Y-%m') AS ym,
  COUNT(*) AS order_cnt,
  SUM(total_price) AS total_amount,
  AVG(total_price) AS avg_amount,
  MAX(total_price) AS max_amount,
  MIN(total_price) AS min_amount
FROM paimon_order
GROUP BY DATE_FORMAT(CAST(order_date AS TIMESTAMP), '%Y-%m')
ORDER BY total_amount DESC, order_cnt DESC;
```


## 2. 按客户统计消费，并过滤高价值客户

- StarRocks
21 rows in set (3.49 sec)
```sql
SELECT
  cust_key,
  COUNT(*) AS order_cnt,
  SUM(total_price) AS total_amount,
  AVG(total_price) AS avg_amount,
  MAX(total_price) AS max_amount
FROM paimon_order
GROUP BY cust_key
HAVING COUNT(*) >= 5
   AND SUM(total_price) > 100000
ORDER BY total_amount DESC, order_cnt DESC;
```

- Flink
21 rows in set (4.37 seconds)
```sql
SELECT
  cust_key,
  COUNT(*) AS order_cnt,
  SUM(total_price) AS total_amount,
  AVG(CAST(total_price AS DOUBLE)) AS avg_amount,
  MAX(total_price) AS max_amount
FROM paimon_order
GROUP BY cust_key
HAVING COUNT(*) >= 5
   AND SUM(total_price) > 100000
ORDER BY total_amount DESC, order_cnt DESC;
```

## 3. 每个月每个优先级的订单占比

- StarRocks
3 rows in set (6.77 sec)
```sql
WITH base AS (
  SELECT
    DATE_FORMAT(order_date, '%Y-%m') AS ym,
    order_priority,
    COUNT(*) AS cnt,
    SUM(total_price) AS amount
  FROM paimon_order
  GROUP BY DATE_FORMAT(order_date, '%Y-%m'), order_priority
),
month_total AS (
  SELECT
    ym,
    SUM(cnt) AS total_cnt,
    SUM(amount) AS total_amount
  FROM base
  GROUP BY ym
)
SELECT
  b.ym,
  b.order_priority,
  b.cnt,
  b.amount,
  b.cnt * 1.0 / t.total_cnt AS cnt_ratio,
  b.amount * 1.0 / t.total_amount AS amount_ratio
FROM base b
JOIN month_total t
  ON b.ym = t.ym
ORDER BY b.ym, b.amount DESC;
```

- Flink
3 rows in set (5.83 seconds)
```sql
WITH base AS (
  SELECT
    DATE_FORMAT(CAST(order_date AS TIMESTAMP), '%Y-%m') AS ym,
    order_priority,
    COUNT(*) AS cnt,
    SUM(total_price) AS amount
  FROM paimon_order
  GROUP BY DATE_FORMAT(CAST(order_date AS TIMESTAMP), '%Y-%m'), order_priority
),
month_total AS (
  SELECT
    ym,
    SUM(cnt) AS total_cnt,
    SUM(amount) AS total_amount
  FROM base
  GROUP BY ym
)
SELECT
  b.ym,
  b.order_priority,
  b.cnt,
  b.amount,
  b.cnt * 1.0 / t.total_cnt AS cnt_ratio,
  b.amount * 1.0 / t.total_amount AS amount_ratio
FROM base b
JOIN month_total t
  ON b.ym = t.ym
ORDER BY b.ym, b.amount DESC;
```

## 4. 窗口函数：每个客户按时间排序，计算累计消费和最近一单

- StarRocks
3413206 rows in set (5.64 sec)
```sql
SELECT
  cust_key,
  order_key,
  order_date,
  total_price,
  SUM(total_price) OVER (
    PARTITION BY cust_key
    ORDER BY order_date
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
  ) AS running_amount,
  ROW_NUMBER() OVER (
    PARTITION BY cust_key
    ORDER BY order_date DESC, order_key DESC
  ) AS rn
FROM paimon_order;
```

- Flink
attempt1:
1m 11s 820ms
[ERROR] Could not execute SQL statement. Reason:
java.lang.OutOfMemoryError: Java heap space
随后K8S自动部署了更多taskmanager容器
attempt2:
5m 49s 674ms
[ERROR] Could not execute SQL statement. Reason:
org.apache.flink.util.FlinkExpectedException: The TaskExecutor is shutting down.
```sql
SELECT
  cust_key,
  order_key,
  order_date,
  total_price,
  SUM(total_price) OVER (
    PARTITION BY cust_key
    ORDER BY order_date
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
  ) AS running_amount,
  ROW_NUMBER() OVER (
    PARTITION BY cust_key
    ORDER BY order_date DESC, order_key DESC
  ) AS rn
FROM paimon_order;
```

## 5. 取每个客户最近 3 笔订单

- StarRocks
63 rows in set (4.73 sec)
```sql
WITH ranked AS (
  SELECT
    cust_key,
    order_key,
    order_date,
    total_price,
    order_priority,
    ROW_NUMBER() OVER (
      PARTITION BY cust_key
      ORDER BY order_date DESC, order_key DESC
    ) AS rn
  FROM paimon_order
)
SELECT *
FROM ranked
WHERE rn <= 3;
```

- Flink
63 rows in set (10.78 seconds)
```sql
WITH ranked AS (
  SELECT
    cust_key,
    order_key,
    order_date,
    total_price,
    order_priority,
    ROW_NUMBER() OVER (
      PARTITION BY cust_key
      ORDER BY order_date DESC, order_key DESC
    ) AS rn
  FROM paimon_order
)
SELECT *
FROM ranked
WHERE rn <= 3;
```


## 6. 自关联：找出同一客户在 30 天内金额逐步上升的订单对

- StarRocks
ERROR 1064 (HY000): Query reached its timeout of 300 seconds, please increase the 'query_timeout' session variable, pending time:0
```sql
SELECT
  a.cust_key,
  a.order_key AS order_key_1,
  a.order_date AS order_date_1,
  a.total_price AS price_1,
  b.order_key AS order_key_2,
  b.order_date AS order_date_2,
  b.total_price AS price_2
FROM paimon_order a
JOIN paimon_order b
  ON a.cust_key = b.cust_key
 AND a.order_key <> b.order_key
 AND b.order_date > a.order_date
 AND b.order_date <= DATE_ADD(a.order_date, 30)
 AND b.total_price > a.total_price;
```

- Flink
30分钟还没算完，不再测试
```sql
SELECT
  a.cust_key,
  a.order_key AS order_key_1,
  a.order_date AS order_date_1,
  a.total_price AS price_1,
  b.order_key AS order_key_2,
  b.order_date AS order_date_2,
  b.total_price AS price_2
FROM paimon_order a
JOIN paimon_order b
  ON a.cust_key = b.cust_key
 AND a.order_key <> b.order_key
 AND b.order_date > a.order_date
 AND b.order_date <= a.order_date + INTERVAL '30' DAY
 AND b.total_price > a.total_price;
```

## 7. 多层子查询：找出消费金额高于客户自身平均值的订单

- StarRocks
1707459 rows in set (9.70 sec)
```sql
SELECT t.*
FROM paimon_order t
JOIN (
  SELECT
    cust_key,
    AVG(total_price) AS avg_price
  FROM paimon_order
  GROUP BY cust_key
) x
ON t.cust_key = x.cust_key
WHERE t.total_price > x.avg_price
ORDER BY t.cust_key, t.total_price DESC;
```

- Flink
[ERROR] Could not execute SQL statement. Reason:
java.lang.OutOfMemoryError: Java heap space
```sql
SELECT t.*
FROM paimon_order t
JOIN (
  SELECT
    cust_key,
    AVG(CAST(total_price AS DOUBLE)) AS avg_price
  FROM paimon_order
  GROUP BY cust_key
) x
ON t.cust_key = x.cust_key
WHERE CAST(t.total_price AS DOUBLE) > x.avg_price
ORDER BY t.cust_key, t.total_price DESC;
```

## 8. TopN：每个月金额最高的前 10 笔订单

- StarRocks
10 rows in set (4.25 sec)
```sql
WITH ranked AS (
  SELECT
    DATE_FORMAT(order_date, '%Y-%m') AS ym,
    order_key,
    cust_key,
    total_price,
    order_date,
    ROW_NUMBER() OVER (
      PARTITION BY DATE_FORMAT(order_date, '%Y-%m')
      ORDER BY total_price DESC, order_date DESC, order_key DESC
    ) AS rn
  FROM paimon_order
)
SELECT *
FROM ranked
WHERE rn <= 10;
```

- Flink
10 rows in set (15.93 seconds)
```sql
WITH ranked AS (
  SELECT
    DATE_FORMAT(CAST(order_date AS TIMESTAMP), '%Y-%m') AS ym,
    order_key,
    cust_key,
    total_price,
    order_date,
    ROW_NUMBER() OVER (
      PARTITION BY DATE_FORMAT(CAST(order_date AS TIMESTAMP), '%Y-%m')
      ORDER BY total_price DESC, order_date DESC, order_key DESC
    ) AS rn
  FROM paimon_order
)
SELECT *
FROM ranked
WHERE rn <= 10;
```

## 9. 组合聚合：同时统计客户、优先级、营业员维度

- StarRocks
252 rows in set (4.45 sec)
```sql
SELECT
  cust_key,
  order_priority,
  clerk,
  COUNT(*) AS order_cnt,
  SUM(total_price) AS total_amount,
  AVG(total_price) AS avg_amount
FROM paimon_order
GROUP BY cust_key, order_priority, clerk
HAVING COUNT(*) >= 3
ORDER BY total_amount DESC;
```

- Flink
252 rows in set (3.92 seconds)
```sql
SELECT
  cust_key,
  order_priority,
  clerk,
  COUNT(*) AS order_cnt,
  SUM(CAST(total_price AS DOUBLE)) AS total_amount,
  AVG(CAST(total_price AS DOUBLE)) AS avg_amount
FROM paimon_order
GROUP BY cust_key, order_priority, clerk
HAVING COUNT(*) >= 3
ORDER BY total_amount DESC;
```
