## 数据分布

Flink SQL> SELECT
>     cust_key,
>     cust_name,
>     COUNT(*) AS order_cnt
> FROM enriched_orders
> GROUP BY cust_key, cust_name
> ORDER BY order_cnt DESC
+----------+-------------+-----------+
| cust_key |   cust_name | order_cnt |
+----------+-------------+-----------+
|        2 |  Customer_2 |   1706376 |
|        3 |  Customer_3 |    568874 |
|        4 |  Customer_4 |    284341 |
|        5 |  Customer_5 |    170725 |
|        6 |  Customer_6 |    113951 |
|        7 |  Customer_7 |     80931 |
|        8 |  Customer_8 |     61475 |
|        9 |  Customer_9 |     47570 |
|       10 | Customer_10 |     37506 |
|        1 |  Customer_1 |     33980 |
+----------+-------------+-----------+
10 rows in set (4.01 seconds)

Flink SQL> SELECT
>     nation_name,
>     COUNT(*) AS order_cnt
> FROM enriched_orders
> GROUP BY nation_name
> ORDER BY order_cnt DESC
> LIMIT 25;
+---------------+-----------+
|   nation_name | order_cnt |
+---------------+-----------+
| UNITED STATES |   1707224 |
|        JORDAN |    567929 |
|         CHINA |    341535 |
| OTHER_NATIONS |    341294 |
|         JAPAN |    284521 |
|       GERMANY |    170703 |
+---------------+-----------+
6 rows in set (1.69 seconds)

Flink SQL> SELECT
>     SUM(CASE WHEN cust_key IS NULL OR cust_key = -1 THEN 1 ELSE 0 END) AS invalid_cust_cnt,
>     SUM(CASE WHEN nation_name IS NULL OR nation_name = '' THEN 1 ELSE 0 END) AS null_nation_cnt,
>     SUM(CASE WHEN clerk IS NULL OR clerk = '' THEN 1 ELSE 0 END) AS null_clerk_cnt,
>     SUM(CASE WHEN order_date IS NULL THEN 1 ELSE 0 END) AS null_date_cnt
> FROM enriched_orders;
+------------------+-----------------+----------------+---------------+
| invalid_cust_cnt | null_nation_cnt | null_clerk_cnt | null_date_cnt |
+------------------+-----------------+----------------+---------------+
|                0 |               0 |              0 |             0 |
+------------------+-----------------+----------------+---------------+
1 row in set (1.61 seconds)

Flink SQL> SELECT
>     clerk,
>     COUNT(*) AS order_cnt
> FROM enriched_orders
> GROUP BY clerk
> ORDER BY order_cnt DESC
> LIMIT 10;
+---------+-----------+
|   clerk | order_cnt |
+---------+-----------+
| Clerk_4 |    849096 |
| Clerk_5 |    847488 |
| Clerk_3 |    564812 |
| Clerk_6 |    563937 |
| Clerk_7 |    235732 |
| Clerk_2 |    235230 |
| Clerk_1 |     55224 |
| Clerk_8 |     54442 |
| Clerk_9 |      3660 |
| Clerk_0 |      3585 |
+---------+-----------+
10 rows in set (1.21 seconds)

Flink SQL> SELECT
>     order_date,
>     COUNT(*) AS order_cnt
> FROM enriched_orders
> GROUP BY order_date
> ORDER BY order_cnt DESC
> LIMIT 10;
+------------+-----------+
| order_date | order_cnt |
+------------+-----------+
| 2026-03-25 |   3393359 |
| 2026-03-24 |     19847 |
+------------+-----------+
2 rows in set (1.10 seconds)


## 优化过程

### 第一版

```sql
SET parallelism.default = '2';
SELECT
    order_date,
    nation_name,
    COUNT(DISTINCT cust_key) AS cust_cnt,
    COUNT(DISTINCT clerk) AS clerk_cnt,
    COUNT(*) AS total_orders,
    SUM(total_price) AS total_price
FROM enriched_orders
GROUP BY order_date, nation_name;
```

[dataskew_1.png]

### 第二版

```sql
SET parallelism.default = '2';
SET table.exec.mini-batch.enabled = true;
SET table.exec.mini-batch.allow-latency = '5s';
SET table.exec.mini-batch.size = '5000';
SELECT
    order_date,
    nation_name,
    COUNT(DISTINCT cust_key) AS cust_cnt,
    COUNT(DISTINCT clerk) AS clerk_cnt,
    COUNT(*) AS total_orders,
    SUM(total_price) AS total_price
FROM enriched_orders
GROUP BY order_date, nation_name;
```

[dataskew_2.png]

### 第三版

```sql
SET parallelism.default = '2';
SET table.optimizer.agg-phase-strategy = 'TWO_PHASE';
SELECT
    order_date,
    nation_name,
    COUNT(DISTINCT cust_key) AS cust_cnt,
    COUNT(DISTINCT clerk) AS clerk_cnt,
    COUNT(*) AS total_orders,
    SUM(total_price) AS total_price
FROM enriched_orders
GROUP BY order_date, nation_name;
```

[dataskew_3.png]

### 第四版

```sql
SET parallelism.default = '2';
SET table.optimizer.distinct-agg.split.enabled = true;
SELECT
    order_date,
    nation_name,
    COUNT(DISTINCT cust_key) AS cust_cnt,
    COUNT(DISTINCT clerk) AS clerk_cnt,
    COUNT(*) AS total_orders,
    SUM(total_price) AS total_price
FROM enriched_orders
GROUP BY order_date, nation_name;
```

[dataskew_4.png]

### 第五版

```sql
SET parallelism.default = '2';
SET table.exec.mini-batch.enabled = true;
SET table.exec.mini-batch.allow-latency = '5s';
SET table.exec.mini-batch.size = '5000';
SET table.optimizer.agg-phase-strategy = 'TWO_PHASE';
SET table.optimizer.distinct-agg.split.enabled = true;
SELECT
    order_date,
    nation_name,
    COUNT(DISTINCT cust_key) AS cust_cnt,
    COUNT(DISTINCT clerk) AS clerk_cnt,
    COUNT(*) AS total_orders,
    SUM(total_price) AS total_price
FROM enriched_orders
GROUP BY order_date, nation_name;
```

[dataskew_5.png]

## 结论

性能：第二版>第五版>...
当前任务下，只打开mini-batch性能最好
