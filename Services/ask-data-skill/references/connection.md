# 连接与引擎选择

## 引擎优先级

**StarRocks 优先**，查询速度快，适合 OLAP 分析。Flink SQL 作为备选（当 StarRocks 不可用或需要流式处理时）。

## 连接步骤

### 前置：SSH 连接远程服务器

```bash
ssh root@47.110.248.69
```

> 已配置免密登录，无需密码。

### StarRocks（默认）

SSH 登录后执行：

```bash
mysql -uroot -h 127.0.0.1 -P 30930
```

进入 mysql 客户端后切换到 Paimon Catalog：

```sql
SET CATALOG paimon_catalog;
```

### Flink SQL（备选）

SSH 登录后执行：

```bash
kubectl exec -it -n lakehouse deploy/airflow -- /opt/flink/bin/sql-client.sh
```

进入 Flink SQL Client 后创建并使用 Catalog：

```sql
CREATE CATALOG paimon_catalog WITH (
    'type' = 'paimon',
    'warehouse' = 's3://fluss/paimon',
    's3.endpoint' = 'https://oss-cn-hangzhou-internal.aliyuncs.com',
    's3.access-key' = 'xxxxxxxxxxxxxxxxxxxxxxxx',
    's3.secret-key' = 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
    's3.path.style.access' = 'false'
);
USE CATALOG paimon_catalog;
```

## 元数据查询命令

连接成功后，使用以下命令获取表结构信息：

```sql
-- 查看所有数据库
SHOW DATABASES;

-- 切换数据库
USE <database_name>;

-- 查看当前库所有表
SHOW TABLES;

-- 查看表结构（字段名、类型、comment）
DESCRIBE <table_name>;

-- 查看完整建表语句（含分区信息、表 comment）
SHOW CREATE TABLE <table_name>;

-- 获取分区表的最大分区
SELECT MAX(pt) FROM <table_name>;
```

## 执行 SQL 并获取结果

### StarRocks 下执行

通过 SSH 管道执行 SQL 并获取结果：

```bash
# 小结果集：直接在终端输出
ssh root@47.110.248.69 "mysql -uroot -h 127.0.0.1 -P 30930 -e \"SET CATALOG paimon_catalog; USE <db>; <YOUR_SQL>;\""

# 大结果集：远程写文件再 SCP 回本地
ssh root@47.110.248.69 "mysql -uroot -h 127.0.0.1 -P 30930 -e \"SET CATALOG paimon_catalog; USE <db>; <YOUR_SQL>;\" > /tmp/query_result.csv"
scp root@47.110.248.69:/tmp/query_result.csv <local_download_path>
ssh root@47.110.248.69 "rm -f /tmp/query_result.csv"
```

### 判断结果集大小

- 先执行 `SELECT COUNT(*) FROM (<YOUR_SQL>) t` 获取行数
- **≤1000 行**：直接解析终端输出，本地写 CSV
- **>1000 行**：远程写文件 → SCP 回本地 → 清理远程临时文件

## 跨平台注意事项

- Mac/Linux：直接使用 `ssh` 和 `scp` 命令
- Windows：使用 PowerShell 中的 `ssh` 和 `scp`（Windows 10+ 内置 OpenSSH）
