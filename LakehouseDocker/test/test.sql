SET 'table.exec.sink.not-null-enforcer'='DROP';
SET 'table.exec.sink.upsert-materialize' = 'NONE';
SET 'execution.checkpointing.interval' = '1min';

CREATE TEMPORARY TABLE source_order (
    `order_key` BIGINT,
    `cust_key` INT,
    `total_price` DECIMAL(15, 2),
    `order_date` TIMESTAMP(3),
    `order_priority_code` INT,
    `clerk_code` INT
) WITH (
  'connector' = 'datagen',
  'rows-per-second' = '1000',
  'number-of-rows' = '100000',
  'fields.order_key.min' = '0',
  'fields.order_key.max' = '100000000',
  'fields.cust_key.min' = '0',
  'fields.cust_key.max' = '20',
  'fields.total_price.min' = '1',
  'fields.total_price.max' = '1000',
  'fields.order_priority_code.min' = '1',
  'fields.order_priority_code.max' = '3',
  'fields.clerk_code.min' = '1',
  'fields.clerk_code.max' = '4'
);

CREATE TEMPORARY TABLE source_customer (
    `cust_key` INT,
    `name_code` INT,
    `phone_code` BIGINT,
    `nation_key` INT NOT NULL,
    `acctbal` DECIMAL(15, 2),
    `mktsegment_code` INT,
    PRIMARY KEY (`cust_key`) NOT ENFORCED
) WITH (
  'connector' = 'datagen',
  'number-of-rows' = '200',
  'fields.cust_key.min' = '0',
  'fields.cust_key.max' = '20',
  'fields.name_code.min' = '1',
  'fields.name_code.max' = '10',
  'fields.phone_code.min' = '1000000000',
  'fields.phone_code.max' = '9999999999',
  'fields.nation_key.min' = '1',
  'fields.nation_key.max' = '5',
  'fields.acctbal.min' = '1',
  'fields.acctbal.max' = '1000',
  'fields.mktsegment_code.min' = '1',
  'fields.mktsegment_code.max' = '5'
);

CREATE TEMPORARY TABLE `source_nation` (
  `nation_key` INT NOT NULL,
  `name_code` INT,
   PRIMARY KEY (`nation_key`) NOT ENFORCED
) WITH (
  'connector' = 'datagen',
  'number-of-rows' = '100',
  'fields.nation_key.min' = '1',
  'fields.nation_key.max' = '5',
  'fields.name_code.min' = '1',
  'fields.name_code.max' = '5'
);


CREATE CATALOG paimon_catalog WITH (
    'type' = 'paimon',
    'warehouse' = 's3://fluss/paimon',
    's3.endpoint' = '<your-oss-endpoint>',
    's3.access-key' = '<your-oss-access-key>',
    's3.secret-key' = '<your-oss-secret-key>',
    's3.path.style.access' = 'false'
);

USE CATALOG paimon_catalog;

CREATE DATABASE IF NOT EXISTS test_db;
USE test_db;

CREATE TABLE paimon_order (
    `order_key` BIGINT,
    `cust_key` INT NOT NULL,
    `total_price` DECIMAL(15, 2),
    `order_date` DATE,
    `order_priority` STRING,
    `clerk` STRING,
    PRIMARY KEY (`order_key`) NOT ENFORCED
);

CREATE TABLE paimon_customer (
    `cust_key` INT NOT NULL,
    `name` STRING,
    `phone` STRING,
    `nation_key` INT NOT NULL,
    `acctbal` DECIMAL(15, 2),
    `mktsegment` STRING,
    PRIMARY KEY (`cust_key`) NOT ENFORCED
);

CREATE TABLE paimon_nation (
  `nation_key` INT NOT NULL,
  `name`       STRING,
   PRIMARY KEY (`nation_key`) NOT ENFORCED
);

EXECUTE STATEMENT SET
BEGIN
    INSERT INTO paimon_nation
    SELECT nation_key,
           CASE name_code
               WHEN 1 THEN 'CANADA'
               WHEN 2 THEN 'JORDAN'
               WHEN 3 THEN 'CHINA'
               WHEN 4 THEN 'UNITED STATES'
               ELSE 'INDIA'
           END
    FROM `default_catalog`.`default_database`.source_nation;

    INSERT INTO paimon_customer
    SELECT cust_key,
           CONCAT('Customer_', CAST(name_code AS STRING)),
           CONCAT('+1-', CAST(phone_code AS STRING)),
           nation_key,
           acctbal,
           CASE mktsegment_code
               WHEN 1 THEN 'AUTOMOBILE'
               WHEN 2 THEN 'BUILDING'
               WHEN 3 THEN 'FURNITURE'
               WHEN 4 THEN 'MACHINERY'
               ELSE 'HOUSEHOLD'
           END
    FROM `default_catalog`.`default_database`.source_customer;

    INSERT INTO paimon_order
    SELECT order_key,
           cust_key,
           total_price,
           CAST(order_date AS DATE),
           CASE order_priority_code
               WHEN 1 THEN 'low'
               WHEN 2 THEN 'medium'
               ELSE 'high'
           END,
           CONCAT('Clerk', CAST(clerk_code AS STRING))
    FROM `default_catalog`.`default_database`.source_order;
END;


CREATE TABLE enriched_orders (
    `order_key` BIGINT,
    `cust_key` INT NOT NULL,
    `total_price` DECIMAL(15, 2),
    `order_date` DATE,
    `order_priority` STRING,
    `clerk` STRING,
    `cust_name` STRING,
    `cust_phone` STRING,
    `cust_acctbal` DECIMAL(15, 2),
    `cust_mktsegment` STRING,
    `nation_name` STRING,
    PRIMARY KEY (`order_key`) NOT ENFORCED
);


SET 'parallelism.default' = '2';
SET 'execution.checkpointing.storage' = 'filesystem';
SET 'execution.checkpointing.dir' = 's3://fluss/flink-checkpoints';
SET 'execution.checkpointing.interval' = '5min';
SET 'execution.checkpointing.timeout' = '15min';
SET 'execution.checkpointing.min-pause' = '30s';
SET 'state.backend.type' = 'rocksdb';
SET 'state.backend.incremental' = 'true';
SET 'table.exec.sink.not-null-enforcer'='DROP';
SET 'table.exec.sink.upsert-materialize' = 'NONE';
-- SET table.exec.mini-batch.enabled = true;
-- SET table.exec.mini-batch.allow-latency = '5s';
-- SET table.exec.mini-batch.size = '5000';
INSERT INTO enriched_orders
SELECT o.order_key,
       o.cust_key,
       o.total_price,
       o.order_date,
       o.order_priority,
       o.clerk,
       c.name,
       c.phone,
       c.acctbal,
       c.mktsegment,
       n.name
FROM paimon_order o
LEFT JOIN paimon_customer c
    ON o.cust_key = c.cust_key
LEFT JOIN paimon_nation n
    ON c.nation_key = n.nation_key;

-- switch to batch mode
SET 'execution.runtime-mode' = 'batch';
SET 'sql-client.execution.result-mode' = 'tableau';

-- sum prices of all enriched orders
SELECT sum(total_price) as sum_price FROM enriched_orders;
