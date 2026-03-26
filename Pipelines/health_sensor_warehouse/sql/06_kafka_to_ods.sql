-- ============================================================
-- 06_kafka_to_ods.sql — Streaming: Kafka → Paimon ODS
-- 运行模式：STREAMING（长期运行的流作业）
-- ============================================================

-- 切换到流模式
SET 'execution.runtime-mode' = 'streaming';
SET 'execution.checkpointing.interval' = '1min';
SET 'execution.checkpointing.min-pause' = '30s';
SET 'table.exec.sink.not-null-enforcer' = 'DROP';
SET 'table.exec.sink.upsert-materialize' = 'NONE';

USE CATALOG paimon_catalog;
USE bhdw;

-- ---- Kafka Source: 统一 topic，所有传感器混合 ---------------
CREATE TEMPORARY TABLE kafka_sensor_event (
    `device_id`              STRING,
    `sensor_type`            STRING,
    `event_ts`               BIGINT,
    `payload`                MAP<STRING, STRING>,
    `event_time` AS TO_TIMESTAMP_LTZ(`event_ts`, 3),
    WATERMARK FOR `event_time` AS `event_time` - INTERVAL '10' SECOND
) WITH (
    'connector' = 'kafka',
    'topic' = 'health_ring_sensor_event',
    'properties.bootstrap.servers' = 'kafka:9094',
    'properties.group.id' = 'flink-health-ring-ods',
    'scan.startup.mode' = 'earliest-offset',
    'format' = 'json',
    'json.ignore-parse-errors' = 'true'
);

-- ---- ODS: 原始传感器事件（统一宽表，按 sensor_type 区分）----
CREATE TABLE IF NOT EXISTS bhdw.ods_sensor_raw_event (
    `device_id`              STRING,
    `sensor_type`            STRING,
    `event_ts`               BIGINT,
    `event_time`             TIMESTAMP(3),
    `ds`                     STRING,
    `hh`                     STRING,
    -- hrm
    `HR`                     DOUBLE,
    -- acc / gyr
    `x`                      DOUBLE,
    `y`                      DOUBLE,
    `z`                      DOUBLE,
    -- grv (extra w)
    `w`                      DOUBLE,
    -- ppg
    `ppg`                    DOUBLE,
    -- ped
    `steps`                  INT,
    `steps_walking`          INT,
    `steps_running`          INT,
    `distance`               DOUBLE,
    `calories`               DOUBLE,
    -- lit
    `ambient_light_intensity` DOUBLE,
    PRIMARY KEY (`device_id`, `sensor_type`, `event_ts`) NOT ENFORCED
);

-- ---- 实时写入：从 Kafka 解析 payload 写入 Paimon ------------
INSERT INTO bhdw.ods_sensor_raw_event
SELECT
    device_id,
    sensor_type,
    event_ts,
    TO_TIMESTAMP_LTZ(event_ts, 3)                             AS event_time,
    DATE_FORMAT(TO_TIMESTAMP_LTZ(event_ts, 3), 'yyyy-MM-dd')  AS ds,
    DATE_FORMAT(TO_TIMESTAMP_LTZ(event_ts, 3), 'HH')          AS hh,
    -- hrm
    CAST(payload['HR'] AS DOUBLE),
    -- acc / gyr / grv 共用 x, y, z
    CAST(payload['x'] AS DOUBLE),
    CAST(payload['y'] AS DOUBLE),
    CAST(payload['z'] AS DOUBLE),
    -- grv w
    CAST(payload['w'] AS DOUBLE),
    -- ppg
    CAST(payload['ppg'] AS DOUBLE),
    -- ped
    CAST(payload['steps'] AS INT),
    CAST(payload['steps_walking'] AS INT),
    CAST(payload['steps_running'] AS INT),
    CAST(payload['distance'] AS DOUBLE),
    CAST(payload['calories'] AS DOUBLE),
    -- lit
    CAST(payload['ambient_light_intensity'] AS DOUBLE)
FROM kafka_sensor_event;
