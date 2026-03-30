-- ============================================================
-- stream_job.sql — All-Streaming Data Warehouse Pipeline
-- Architecture:  Kafka → ODS → DWD/DIM → DWS
-- Runtime mode:  STREAMING (long-running Flink job)
-- ============================================================

-- ============================================================
-- 00  Runtime Settings & Catalog
-- ============================================================

SET 'execution.runtime-mode' = 'streaming';
SET 'execution.checkpointing.interval' = '5min';
SET 'execution.checkpointing.min-pause' = '1min';
SET 'table.exec.sink.not-null-enforcer' = 'DROP';
SET 'table.exec.sink.upsert-materialize' = 'NONE';

CREATE CATALOG paimon_catalog WITH (
    'type' = 'paimon',
    'warehouse' = 's3://fluss/paimon',
    's3.endpoint' = '<your-endpoint>',
    's3.access-key' = '<your-access-key>',
    's3.secret-key' = '<your-secret-key>',
    's3.path.style.access' = 'false'
);

USE CATALOG paimon_catalog;
CREATE DATABASE IF NOT EXISTS bhdw;
USE bhdw;

-- ============================================================
-- 01  Kafka Source Tables (4 topics)
-- ============================================================

-- ---- 1) kafka_user_profile: 用户个人信息 / 问卷（维度数据）----
CREATE TEMPORARY TABLE kafka_user_profile (
    `device_id`   STRING,
    `sex`         INT,
    `age`         INT,
    `marriage`    INT,
    `occupation`  INT,
    `smartwatch`  INT,
    `regular`     INT,
    `exercise`    INT,
    `coffee`      INT,
    `smoking`     INT,
    `drinking`    INT,
    `height`      DOUBLE,
    `weight`      DOUBLE,
    `ISI_1`       INT,
    `PHQ9_1`      INT,
    `GAD7_1`      INT,
    `MEQ`         INT,
    `ISI_2`       DOUBLE,
    `PHQ9_2`      DOUBLE,
    `GAD7_2`      DOUBLE,
    `ISI_F`       DOUBLE,
    `PHQ9_F`      DOUBLE,
    `GAD7_F`      DOUBLE
) WITH (
    'connector' = 'kafka',
    'topic' = 'kafka_user_profile',
    'properties.bootstrap.servers' = 'kafka:9092',
    'properties.group.id' = 'flink-user-profile',
    'scan.startup.mode' = 'latest-offset',
    'format' = 'json',
    'json.ignore-parse-errors' = 'true'
);

-- ---- 2) kafka_sleep_diary: 睡眠日报（每日一条汇总）----------
CREATE TEMPORARY TABLE kafka_sleep_diary (
    `user_id`          STRING,
    `record_date`      STRING,
    `go2bed`           STRING,
    `asleep`           STRING,
    `wakeup`           STRING,
    `wakeup_at_night`  INT,
    `waso`             DOUBLE,
    `sleep_duration`   DOUBLE,
    `in_bed_duration`  DOUBLE,
    `sleep_latency`    DOUBLE,
    `sleep_efficiency` DOUBLE
) WITH (
    'connector' = 'kafka',
    'topic' = 'kafka_sleep_diary',
    'properties.bootstrap.servers' = 'kafka:9092',
    'properties.group.id' = 'flink-sleep-diary',
    'scan.startup.mode' = 'latest-offset',
    'format' = 'json',
    'json.ignore-parse-errors' = 'true'
);

-- ---- 3) kafka_sensor_hrv: 心率 HRV 5分钟聚合快照 -----------
CREATE TEMPORARY TABLE kafka_sensor_hrv (
    `device_id`        STRING,
    `ts_start`         BIGINT,
    `ts_end`           BIGINT,
    `missingness_score` DOUBLE,
    `HR`               DOUBLE,
    `ibi`              DOUBLE,
    `acc_x_avg`        DOUBLE,
    `acc_y_avg`        DOUBLE,
    `acc_z_avg`        DOUBLE,
    `grv_x_avg`        DOUBLE,
    `grv_y_avg`        DOUBLE,
    `grv_z_avg`        DOUBLE,
    `grv_w_avg`        DOUBLE,
    `gyr_x_avg`        DOUBLE,
    `gyr_y_avg`        DOUBLE,
    `gyr_z_avg`        DOUBLE,
    `steps`            DOUBLE,
    `distance`         DOUBLE,
    `calories`         DOUBLE,
    `light_avg`        DOUBLE,
    `sdnn`             DOUBLE,
    `sdsd`             DOUBLE,
    `rmssd`            DOUBLE,
    `pnn20`            DOUBLE,
    `pnn50`            DOUBLE,
    `lf`               DOUBLE,
    `hf`               DOUBLE,
    `lf_hf_ratio`      DOUBLE,
    `proc_time` AS PROCTIME()
) WITH (
    'connector' = 'kafka',
    'topic' = 'kafka_sensor_hrv',
    'properties.bootstrap.servers' = 'kafka:9092',
    'properties.group.id' = 'flink-sensor-hrv',
    'scan.startup.mode' = 'latest-offset',
    'format' = 'json',
    'json.ignore-parse-errors' = 'true'
);

-- ---- 4) kafka_sensor_event: 传感器日志（统一 topic）---------
CREATE TEMPORARY TABLE kafka_sensor_event (
    `device_id`   STRING,
    `sensor_type` STRING,
    `event_ts`    BIGINT,
    `payload`     MAP<STRING, STRING>,
    `event_time` AS TO_TIMESTAMP_LTZ(`event_ts`, 3),
    WATERMARK FOR `event_time` AS `event_time` - INTERVAL '10' SECOND
) WITH (
    'connector' = 'kafka',
    'topic' = 'kafka_sensor_event',
    'properties.bootstrap.servers' = 'kafka:9092',
    'properties.group.id' = 'flink-sensor-event',
    'scan.startup.mode' = 'latest-offset',
    'format' = 'json',
    'json.ignore-parse-errors' = 'true'
);

-- ============================================================
-- 02  ODS Layer — 原始数据层（10 张表）
-- ============================================================

-- ---- ods_user_profile: 用户个人信息 -------------------------
CREATE TABLE IF NOT EXISTS bhdw.ods_user_profile (
    `device_id`   STRING,
    `sex`         INT,
    `age`         INT,
    `marriage`    INT,
    `occupation`  INT,
    `smartwatch`  INT,
    `regular`     INT,
    `exercise`    INT,
    `coffee`      INT,
    `smoking`     INT,
    `drinking`    INT,
    `height`      DOUBLE,
    `weight`      DOUBLE,
    `ISI_1`       INT,
    `PHQ9_1`      INT,
    `GAD7_1`      INT,
    `MEQ`         INT,
    `ISI_2`       DOUBLE,
    `PHQ9_2`      DOUBLE,
    `GAD7_2`      DOUBLE,
    `ISI_F`       DOUBLE,
    `PHQ9_F`      DOUBLE,
    `GAD7_F`      DOUBLE,
    PRIMARY KEY (`device_id`) NOT ENFORCED
);

-- ---- ods_sleep_diary: 睡眠日记 ------------------------------
CREATE TABLE IF NOT EXISTS bhdw.ods_sleep_diary (
    `user_id`          STRING,
    `record_date`      DATE,
    `go2bed`           STRING,
    `asleep`           STRING,
    `wakeup`           STRING,
    `wakeup_at_night`  INT,
    `waso`             DOUBLE,
    `sleep_duration`   DOUBLE,
    `in_bed_duration`  DOUBLE,
    `sleep_latency`    DOUBLE,
    `sleep_efficiency` DOUBLE,
    PRIMARY KEY (`user_id`, `record_date`) NOT ENFORCED
);

-- ---- ods_sensor_hrv: HRV 5分钟聚合 -------------------------
CREATE TABLE IF NOT EXISTS bhdw.ods_sensor_hrv (
    `device_id`        STRING,
    `ts_start`         BIGINT,
    `ts_end`           BIGINT,
    `missingness_score` DOUBLE,
    `HR`               DOUBLE,
    `ibi`              DOUBLE,
    `acc_x_avg`        DOUBLE,
    `acc_y_avg`        DOUBLE,
    `acc_z_avg`        DOUBLE,
    `grv_x_avg`        DOUBLE,
    `grv_y_avg`        DOUBLE,
    `grv_z_avg`        DOUBLE,
    `grv_w_avg`        DOUBLE,
    `gyr_x_avg`        DOUBLE,
    `gyr_y_avg`        DOUBLE,
    `gyr_z_avg`        DOUBLE,
    `steps`            DOUBLE,
    `distance`         DOUBLE,
    `calories`         DOUBLE,
    `light_avg`        DOUBLE,
    `sdnn`             DOUBLE,
    `sdsd`             DOUBLE,
    `rmssd`            DOUBLE,
    `pnn20`            DOUBLE,
    `pnn50`            DOUBLE,
    `lf`               DOUBLE,
    `hf`               DOUBLE,
    `lf_hf_ratio`      DOUBLE,
    PRIMARY KEY (`device_id`, `ts_start`) NOT ENFORCED
);

-- ---- ods_sensor_acc: 加速度计原始事件 -----------------------
CREATE TABLE IF NOT EXISTS bhdw.ods_sensor_acc (
    `device_id`   STRING,
    `event_ts`    BIGINT,
    `event_time`  TIMESTAMP(3),
    `x`           DOUBLE,
    `y`           DOUBLE,
    `z`           DOUBLE,
    PRIMARY KEY (`device_id`, `event_ts`) NOT ENFORCED
);

-- ---- ods_sensor_grv: 重力传感器原始事件 ---------------------
CREATE TABLE IF NOT EXISTS bhdw.ods_sensor_grv (
    `device_id`   STRING,
    `event_ts`    BIGINT,
    `event_time`  TIMESTAMP(3),
    `x`           DOUBLE,
    `y`           DOUBLE,
    `z`           DOUBLE,
    `w`           DOUBLE,
    PRIMARY KEY (`device_id`, `event_ts`) NOT ENFORCED
);

-- ---- ods_sensor_gyr: 陀螺仪原始事件 ------------------------
CREATE TABLE IF NOT EXISTS bhdw.ods_sensor_gyr (
    `device_id`   STRING,
    `event_ts`    BIGINT,
    `event_time`  TIMESTAMP(3),
    `x`           DOUBLE,
    `y`           DOUBLE,
    `z`           DOUBLE,
    PRIMARY KEY (`device_id`, `event_ts`) NOT ENFORCED
);

-- ---- ods_sensor_hrm: 心率原始事件 ---------------------------
CREATE TABLE IF NOT EXISTS bhdw.ods_sensor_hrm (
    `device_id`   STRING,
    `event_ts`    BIGINT,
    `event_time`  TIMESTAMP(3),
    `HR`          DOUBLE,
    PRIMARY KEY (`device_id`, `event_ts`) NOT ENFORCED
);

-- ---- ods_sensor_lit: 光照传感器原始事件 ---------------------
CREATE TABLE IF NOT EXISTS bhdw.ods_sensor_lit (
    `device_id`              STRING,
    `event_ts`               BIGINT,
    `event_time`             TIMESTAMP(3),
    `ambient_light_intensity` DOUBLE,
    PRIMARY KEY (`device_id`, `event_ts`) NOT ENFORCED
);

-- ---- ods_sensor_ped: 计步器原始事件 -------------------------
CREATE TABLE IF NOT EXISTS bhdw.ods_sensor_ped (
    `device_id`      STRING,
    `event_ts`       BIGINT,
    `event_time`     TIMESTAMP(3),
    `steps`          INT,
    `steps_walking`  INT,
    `steps_running`  INT,
    `distance`       DOUBLE,
    `calories`       DOUBLE,
    PRIMARY KEY (`device_id`, `event_ts`) NOT ENFORCED
);

-- ---- ods_sensor_ppg: PPG 原始事件 ---------------------------
CREATE TABLE IF NOT EXISTS bhdw.ods_sensor_ppg (
    `device_id`   STRING,
    `event_ts`    BIGINT,
    `event_time`  TIMESTAMP(3),
    `ppg`         DOUBLE,
    PRIMARY KEY (`device_id`, `event_ts`) NOT ENFORCED
);

-- ============================================================
-- 03  DWD / DIM Layer — 明细 / 维度层（3 张表）
-- ============================================================

-- ---- dim_user_profile: 用户维度表（含 BMI、等级标签）--------
CREATE TABLE IF NOT EXISTS bhdw.dim_user_profile (
    `device_id`        STRING,
    `sex`              INT,
    `age`              INT,
    `marriage`         INT,
    `occupation`       INT,
    `smartwatch`       INT,
    `regular`          INT,
    `exercise`         INT,
    `coffee`           INT,
    `smoking`          INT,
    `drinking`         INT,
    `height`           DOUBLE,
    `weight`           DOUBLE,
    `bmi`              DOUBLE,
    `ISI_1`            INT,
    `PHQ9_1`           INT,
    `GAD7_1`           INT,
    `MEQ`              INT,
    `ISI_2`            DOUBLE,
    `PHQ9_2`           DOUBLE,
    `GAD7_2`           DOUBLE,
    `ISI_F`            DOUBLE,
    `PHQ9_F`           DOUBLE,
    `GAD7_F`           DOUBLE,
    `insomnia_level`   STRING,
    `depression_level` STRING,
    `anxiety_level`    STRING,
    `chronotype`       STRING,
    PRIMARY KEY (`device_id`) NOT ENFORCED
);

-- ---- dwd_sleep_diary: 睡眠明细（含质量标签）-----------------
CREATE TABLE IF NOT EXISTS bhdw.dwd_sleep_diary (
    `user_id`          STRING,
    `record_date`      DATE,
    `go2bed`           STRING,
    `asleep`           STRING,
    `wakeup`           STRING,
    `wakeup_at_night`  INT,
    `waso`             DOUBLE,
    `sleep_duration`   DOUBLE,
    `in_bed_duration`  DOUBLE,
    `sleep_latency`    DOUBLE,
    `sleep_efficiency` DOUBLE,
    `sleep_quality`    STRING,
    `is_late_sleep`    BOOLEAN,
    PRIMARY KEY (`user_id`, `record_date`) NOT ENFORCED
);

-- ---- dwd_sensor_hrv: HRV 明细（含活动强度、质量标签）--------
CREATE TABLE IF NOT EXISTS bhdw.dwd_sensor_hrv (
    `device_id`        STRING,
    `ts_start`         BIGINT,
    `ts_end`           BIGINT,
    `event_time`       TIMESTAMP(3),
    `ds`               STRING,
    `hh`               STRING,
    `missingness_score` DOUBLE,
    `HR`               DOUBLE,
    `ibi`              DOUBLE,
    `acc_x_avg`        DOUBLE,
    `acc_y_avg`        DOUBLE,
    `acc_z_avg`        DOUBLE,
    `grv_x_avg`        DOUBLE,
    `grv_y_avg`        DOUBLE,
    `grv_z_avg`        DOUBLE,
    `grv_w_avg`        DOUBLE,
    `gyr_x_avg`        DOUBLE,
    `gyr_y_avg`        DOUBLE,
    `gyr_z_avg`        DOUBLE,
    `steps`            DOUBLE,
    `distance`         DOUBLE,
    `calories`         DOUBLE,
    `light_avg`        DOUBLE,
    `sdnn`             DOUBLE,
    `sdsd`             DOUBLE,
    `rmssd`            DOUBLE,
    `pnn20`            DOUBLE,
    `pnn50`            DOUBLE,
    `lf`               DOUBLE,
    `hf`               DOUBLE,
    `lf_hf_ratio`      DOUBLE,
    `activity_intensity` STRING,
    `hrv_quality`      STRING,
    PRIMARY KEY (`device_id`, `ts_start`) NOT ENFORCED
);

-- ============================================================
-- 04  DWS Layer — 汇总层（1 张表，1小时粒度）
-- ============================================================

-- ---- dws_user_report_1h: 用户每小时综合报告 -----------------
-- 以 dwd_sensor_hrv 按小时聚合为驱动，LEFT JOIN 维度和睡眠数据
CREATE TABLE IF NOT EXISTS bhdw.dws_user_report_1h (
    `device_id`            STRING,
    `ds`                   STRING,
    `hh`                   STRING,
    -- 维度属性（Lookup）
    `sex`                  INT,
    `age`                  INT,
    `bmi`                  DOUBLE,
    `insomnia_level`       STRING,
    `depression_level`     STRING,
    `anxiety_level`        STRING,
    `chronotype`           STRING,
    -- 睡眠（当日数据 Lookup）
    `sleep_duration`       DOUBLE,
    `sleep_efficiency`     DOUBLE,
    `sleep_quality`        STRING,
    -- HRV 每小时聚合
    `avg_hr`               DOUBLE,
    `avg_rmssd`            DOUBLE,
    `total_steps`          DOUBLE,
    `total_calories`       DOUBLE,
    `hrv_record_count`     BIGINT,
    PRIMARY KEY (`device_id`, `ds`, `hh`) NOT ENFORCED
);

-- ============================================================
-- 05  Streaming INSERT — Kafka → ODS
-- ============================================================

-- kafka_user_profile → ods_user_profile
INSERT INTO bhdw.ods_user_profile
SELECT * FROM kafka_user_profile;

-- kafka_sleep_diary → ods_sleep_diary
INSERT INTO bhdw.ods_sleep_diary
SELECT
    user_id,
    CAST(record_date AS DATE),
    go2bed,
    asleep,
    wakeup,
    wakeup_at_night,
    waso,
    sleep_duration,
    in_bed_duration,
    sleep_latency,
    sleep_efficiency
FROM kafka_sleep_diary;

-- kafka_sensor_hrv → ods_sensor_hrv
INSERT INTO bhdw.ods_sensor_hrv
SELECT
    device_id, ts_start, ts_end,
    missingness_score, HR, ibi,
    acc_x_avg, acc_y_avg, acc_z_avg,
    grv_x_avg, grv_y_avg, grv_z_avg, grv_w_avg,
    gyr_x_avg, gyr_y_avg, gyr_z_avg,
    steps, distance, calories, light_avg,
    sdnn, sdsd, rmssd, pnn20, pnn50,
    lf, hf, lf_hf_ratio
FROM kafka_sensor_hrv;

-- kafka_sensor_event → ods_sensor_acc
INSERT INTO bhdw.ods_sensor_acc
SELECT
    device_id,
    event_ts,
    TO_TIMESTAMP_LTZ(event_ts, 3),
    CAST(payload['x'] AS DOUBLE),
    CAST(payload['y'] AS DOUBLE),
    CAST(payload['z'] AS DOUBLE)
FROM kafka_sensor_event
WHERE sensor_type = 'acc';

-- kafka_sensor_event → ods_sensor_grv
INSERT INTO bhdw.ods_sensor_grv
SELECT
    device_id,
    event_ts,
    TO_TIMESTAMP_LTZ(event_ts, 3),
    CAST(payload['x'] AS DOUBLE),
    CAST(payload['y'] AS DOUBLE),
    CAST(payload['z'] AS DOUBLE),
    CAST(payload['w'] AS DOUBLE)
FROM kafka_sensor_event
WHERE sensor_type = 'grv';

-- kafka_sensor_event → ods_sensor_gyr
INSERT INTO bhdw.ods_sensor_gyr
SELECT
    device_id,
    event_ts,
    TO_TIMESTAMP_LTZ(event_ts, 3),
    CAST(payload['x'] AS DOUBLE),
    CAST(payload['y'] AS DOUBLE),
    CAST(payload['z'] AS DOUBLE)
FROM kafka_sensor_event
WHERE sensor_type = 'gyr';

-- kafka_sensor_event → ods_sensor_hrm
INSERT INTO bhdw.ods_sensor_hrm
SELECT
    device_id,
    event_ts,
    TO_TIMESTAMP_LTZ(event_ts, 3),
    CAST(payload['HR'] AS DOUBLE)
FROM kafka_sensor_event
WHERE sensor_type = 'hrm';

-- kafka_sensor_event → ods_sensor_lit
INSERT INTO bhdw.ods_sensor_lit
SELECT
    device_id,
    event_ts,
    TO_TIMESTAMP_LTZ(event_ts, 3),
    CAST(payload['ambient_light_intensity'] AS DOUBLE)
FROM kafka_sensor_event
WHERE sensor_type = 'lit';

-- kafka_sensor_event → ods_sensor_ped
INSERT INTO bhdw.ods_sensor_ped
SELECT
    device_id,
    event_ts,
    TO_TIMESTAMP_LTZ(event_ts, 3),
    CAST(payload['steps'] AS INT),
    CAST(payload['steps_walking'] AS INT),
    CAST(payload['steps_running'] AS INT),
    CAST(payload['distance'] AS DOUBLE),
    CAST(payload['calories'] AS DOUBLE)
FROM kafka_sensor_event
WHERE sensor_type = 'ped';

-- kafka_sensor_event → ods_sensor_ppg
INSERT INTO bhdw.ods_sensor_ppg
SELECT
    device_id,
    event_ts,
    TO_TIMESTAMP_LTZ(event_ts, 3),
    CAST(payload['ppg'] AS DOUBLE)
FROM kafka_sensor_event
WHERE sensor_type = 'ppg';

-- ============================================================
-- 06  Streaming INSERT — ODS → DWD / DIM
-- ============================================================

-- ods_user_profile → dim_user_profile（维度转换，加标签）
INSERT INTO bhdw.dim_user_profile
SELECT
    device_id,
    sex, age, marriage, occupation, smartwatch, regular,
    exercise, coffee, smoking, drinking,
    height, weight,
    ROUND(weight / (height / 100.0) / (height / 100.0), 2) AS bmi,
    ISI_1, PHQ9_1, GAD7_1, MEQ,
    ISI_2, PHQ9_2, GAD7_2,
    ISI_F, PHQ9_F, GAD7_F,
    CASE
        WHEN ISI_1 <= 7  THEN 'none'
        WHEN ISI_1 <= 14 THEN 'sub-threshold'
        WHEN ISI_1 <= 21 THEN 'moderate'
        ELSE 'severe'
    END AS insomnia_level,
    CASE
        WHEN PHQ9_1 <= 4  THEN 'minimal'
        WHEN PHQ9_1 <= 9  THEN 'mild'
        WHEN PHQ9_1 <= 14 THEN 'moderate'
        WHEN PHQ9_1 <= 19 THEN 'moderately_severe'
        ELSE 'severe'
    END AS depression_level,
    CASE
        WHEN GAD7_1 <= 4  THEN 'minimal'
        WHEN GAD7_1 <= 9  THEN 'mild'
        WHEN GAD7_1 <= 14 THEN 'moderate'
        ELSE 'severe'
    END AS anxiety_level,
    CASE
        WHEN MEQ <= 30 THEN 'definite_evening'
        WHEN MEQ <= 41 THEN 'moderate_evening'
        WHEN MEQ <= 58 THEN 'intermediate'
        WHEN MEQ <= 69 THEN 'moderate_morning'
        ELSE 'definite_morning'
    END AS chronotype
FROM bhdw.ods_user_profile;

-- ods_sleep_diary → dwd_sleep_diary（加质量标签）
INSERT INTO bhdw.dwd_sleep_diary
SELECT
    user_id,
    record_date,
    go2bed, asleep, wakeup,
    wakeup_at_night,
    waso,
    sleep_duration,
    in_bed_duration,
    sleep_latency,
    sleep_efficiency,
    CASE
        WHEN sleep_efficiency >= 0.85
             AND sleep_duration >= 7.0
             AND sleep_duration <= 9.0 THEN 'good'
        WHEN sleep_efficiency >= 0.75
             AND sleep_duration >= 6.0 THEN 'fair'
        ELSE 'poor'
    END AS sleep_quality,
    CASE
        WHEN asleep > '01:00:00' AND asleep <= '12:00:00' THEN TRUE
        ELSE FALSE
    END AS is_late_sleep
FROM bhdw.ods_sleep_diary;

-- ods_sensor_hrv → dwd_sensor_hrv（加活动强度、HRV质量标签）
INSERT INTO bhdw.dwd_sensor_hrv
SELECT
    device_id,
    ts_start, ts_end,
    TO_TIMESTAMP_LTZ(ts_start, 3)                             AS event_time,
    DATE_FORMAT(TO_TIMESTAMP_LTZ(ts_start, 3), 'yyyy-MM-dd')  AS ds,
    DATE_FORMAT(TO_TIMESTAMP_LTZ(ts_start, 3), 'HH')          AS hh,
    missingness_score, HR, ibi,
    acc_x_avg, acc_y_avg, acc_z_avg,
    grv_x_avg, grv_y_avg, grv_z_avg, grv_w_avg,
    gyr_x_avg, gyr_y_avg, gyr_z_avg,
    steps, distance, calories, light_avg,
    sdnn, sdsd, rmssd, pnn20, pnn50,
    lf, hf, lf_hf_ratio,
    CASE
        WHEN SQRT(acc_x_avg * acc_x_avg + acc_y_avg * acc_y_avg + acc_z_avg * acc_z_avg) < 1.5  THEN 'sedentary'
        WHEN SQRT(acc_x_avg * acc_x_avg + acc_y_avg * acc_y_avg + acc_z_avg * acc_z_avg) < 5.0  THEN 'light'
        WHEN SQRT(acc_x_avg * acc_x_avg + acc_y_avg * acc_y_avg + acc_z_avg * acc_z_avg) < 10.0 THEN 'moderate'
        ELSE 'vigorous'
    END AS activity_intensity,
    CASE
        WHEN missingness_score <= 0.1  THEN 'excellent'
        WHEN missingness_score <= 0.3  THEN 'good'
        WHEN missingness_score <= 0.5  THEN 'fair'
        ELSE 'poor'
    END AS hrv_quality
FROM bhdw.ods_sensor_hrv;

-- ============================================================
-- 07  Streaming INSERT — DWD/DIM → DWS（1小时粒度）
-- ============================================================

-- dws_user_report_1h: 以 HRV 按小时聚合为主表，
-- Lookup Join dim_user_profile 和 dwd_sleep_diary

INSERT INTO bhdw.dws_user_report_1h
SELECT
    h.device_id,
    h.ds,
    h.hh,
    -- 维度属性
    p.sex,
    p.age,
    p.bmi,
    p.insomnia_level,
    p.depression_level,
    p.anxiety_level,
    p.chronotype,
    -- 睡眠（当日）
    s.sleep_duration,
    s.sleep_efficiency,
    s.sleep_quality,
    -- HRV 每小时聚合
    ROUND(h.avg_hr, 2),
    ROUND(h.avg_rmssd, 2),
    h.total_steps,
    h.total_calories,
    h.hrv_record_count
FROM (
    SELECT
        device_id,
        ds,
        hh,
        AVG(HR)       AS avg_hr,
        AVG(rmssd)    AS avg_rmssd,
        SUM(steps)    AS total_steps,
        SUM(calories) AS total_calories,
        COUNT(*)      AS hrv_record_count
    FROM bhdw.dwd_sensor_hrv
    GROUP BY device_id, ds, hh
) h
LEFT JOIN bhdw.dim_user_profile p
    ON h.device_id = p.device_id
LEFT JOIN bhdw.dwd_sleep_diary s
    ON h.device_id = s.user_id
    AND h.ds = CAST(s.record_date AS STRING);
