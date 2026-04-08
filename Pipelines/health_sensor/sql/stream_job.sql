-- ============================================================
-- stream_job.sql — 硬件传感器实时链路
-- Architecture:  Kafka → ODS → DWD → DWS
-- 数据来源：智能手环两种上传模式
--   实时监测模式：1秒/包，蓝牙持续连接，秒级高优先级数据
--   历史同步模式：10分钟/包，蓝牙重连后批量，原始信号+分钟级数据
-- ============================================================

-- ============================================================
-- 00  Runtime Settings & Catalog
-- ============================================================

SET 'execution.runtime-mode' = 'streaming';
SET 'state.backend.type' = 'rocksdb';
SET 'state.checkpoints.dir' = 's3://fluss/flink-checkpoints';
SET 'state.savepoints.dir' = 's3://fluss/flink-savepoints';
SET 'execution.checkpointing.interval' = '10min';
SET 'execution.checkpointing.min-pause' = '3min';
SET 'execution.checkpointing.timeout' = '20min';
SET 'execution.checkpointing.tolerable-failed-checkpoints' = '10';
SET 'table.exec.sink.not-null-enforcer' = 'DROP';
SET 'table.exec.sink.upsert-materialize' = 'NONE';

CREATE CATALOG paimon_catalog WITH (
    'type'                  = 'paimon',
    'warehouse'             = 's3://fluss/paimon',
    's3.endpoint'           = '<your-endpoint>',
    's3.access-key'         = '<your-access-key>',
    's3.secret-key'         = '<your-secret-key>',
    's3.path.style.access'  = 'false'
);

USE CATALOG paimon_catalog;
CREATE DATABASE IF NOT EXISTS bhdw;
USE bhdw;

-- ============================================================
-- 01  Kafka Source Tables
-- ============================================================

-- ---- 1) 实时监测模式：1秒/包，秒级高优先级数据 ---------------
-- 硬件嵌入式计算输出：心率、计步、佩戴检测、体动强度、姿态
CREATE TEMPORARY TABLE kafka_sensor_realtime (
    `device_id`        STRING,
    `event_ts`         BIGINT,          -- 毫秒时间戳
    -- 心率（秒级）
    `heart_rate`       INT,             -- bpm
    `avg_heart_rate`   INT,             -- 滑动平均心率 bpm
    -- 计步（秒级累计）
    `steps`            INT,
    -- 佩戴检测（秒级）：1=佩戴 0=未佩戴
    `wearing`          INT,
    -- 体动强度（秒级）：0=静止 1=轻度 2=中度 3=剧烈
    `activity_level`   INT,
    -- 姿态（秒级）：sit/stand/lie
    `posture`          STRING,
    `event_time` AS TO_TIMESTAMP_LTZ(`event_ts`, 3),
    WATERMARK FOR `event_time` AS `event_time` - INTERVAL '5' SECOND
) WITH (
    'connector'                     = 'kafka',
    'topic'                         = 'kafka_sensor_realtime',
    'properties.bootstrap.servers'  = 'kafka:9092',
    'properties.group.id'           = 'flink-sensor-realtime',
    'scan.startup.mode'             = 'latest-offset',
    'format'                        = 'json',
    'json.ignore-parse-errors'      = 'true'
);

-- ---- 2) APP用户信息：用户注册/问卷，维度数据 ----------------
CREATE TEMPORARY TABLE kafka_user_profile (
    `device_id`   STRING,
    `user_id`     STRING,
    `sex`         INT,             -- 0=女 1=男
    `age`         INT,
    `height`      DOUBLE,          -- cm
    `weight`      DOUBLE,          -- kg
    `ISI`         INT,             -- 失眠严重程度指数
    `PHQ9`        INT,             -- 抑郁量表
    `GAD7`        INT,             -- 焦虑量表
    `MEQ`         INT              -- 睡眠时型问卷
) WITH (
    'connector'                     = 'kafka',
    'topic'                         = 'kafka_user_profile',
    'properties.bootstrap.servers'  = 'kafka:9092',
    'properties.group.id'           = 'flink-user-profile',
    'scan.startup.mode'             = 'earliest-offset',
    'format'                        = 'json',
    'json.ignore-parse-errors'      = 'true'
);

-- ---- 3) 历史同步模式：10分钟/包，原始信号 + 分钟级指标 -------
CREATE TEMPORARY TABLE kafka_sensor_history (
    `device_id`        STRING,
    `ts_start`         BIGINT,          -- 包起始时间戳（毫秒）
    `ts_end`           BIGINT,          -- 包结束时间戳（毫秒）
    -- 分钟级心率
    `heart_rate_min`   DOUBLE,
    -- 分钟级HRV指标
    `rmssd`            DOUBLE,
    `sdnn`             DOUBLE,
    `pnn50`            DOUBLE,
    `lf_hf_ratio`      DOUBLE,
    -- 分钟级血氧
    `spo2`             DOUBLE,          -- %
    -- 分钟级呼吸率
    `resp_rate`        DOUBLE,          -- 次/分钟
    -- 分钟级皮肤温度（滤波后）
    `skin_temp`        DOUBLE,          -- °C
    -- 分钟级计步
    `steps_min`        INT,
    -- 分钟级体动强度（均值）
    `activity_level_min` DOUBLE,
    -- 分钟级姿态（众数）
    `posture_min`      STRING,
    -- 佩戴检测（秒级，分钟内有效采样比例）
    `wearing_ratio`    DOUBLE,          -- 0.0~1.0
    -- PPG原始信号（25~200Hz，按分钟存储）
    `ppg_raw`          ARRAY<DOUBLE>,
    -- IMU六轴原始信号（10~50Hz）
    `acc_x_raw`        ARRAY<DOUBLE>,
    `acc_y_raw`        ARRAY<DOUBLE>,
    `acc_z_raw`        ARRAY<DOUBLE>,
    `gyr_x_raw`        ARRAY<DOUBLE>,
    `gyr_y_raw`        ARRAY<DOUBLE>,
    `gyr_z_raw`        ARRAY<DOUBLE>,
    -- 生物电阻抗原始数据（0.1~1Hz）
    `bia_raw`          ARRAY<DOUBLE>,
    `event_time` AS TO_TIMESTAMP_LTZ(`ts_start`, 3),
    WATERMARK FOR `event_time` AS `event_time` - INTERVAL '30' SECOND
) WITH (
    'connector'                     = 'kafka',
    'topic'                         = 'kafka_sensor_history',
    'properties.bootstrap.servers'  = 'kafka:9092',
    'properties.group.id'           = 'flink-sensor-history',
    'scan.startup.mode'             = 'latest-offset',
    'format'                        = 'json',
    'json.ignore-parse-errors'      = 'true'
);

-- ============================================================
-- 02  DIM Layer — 维度层
-- ============================================================

CREATE TABLE IF NOT EXISTS bhdw.dim_user (
    `device_id`        STRING,
    `user_id`          STRING,
    `sex`              INT,
    `age`              INT,
    `height`           DOUBLE,
    `weight`           DOUBLE,
    `bmi`              DOUBLE,
    `ISI`              INT,
    `PHQ9`             INT,
    `GAD7`             INT,
    `MEQ`              INT,
    `insomnia_level`   STRING,   -- none/sub-threshold/moderate/severe
    `depression_level` STRING,   -- minimal/mild/moderate/moderately_severe/severe
    `anxiety_level`    STRING,   -- minimal/mild/moderate/severe
    `chronotype`       STRING,   -- definite_evening/.../definite_morning
    PRIMARY KEY (`device_id`) NOT ENFORCED
);

-- ============================================================
-- 03  ODS Layer — 原始数据层
-- ============================================================

CREATE TABLE IF NOT EXISTS bhdw.ods_user_profile (
    `device_id`   STRING,
    `user_id`     STRING,
    `sex`         INT,
    `age`         INT,
    `height`      DOUBLE,
    `weight`      DOUBLE,
    `ISI`         INT,
    `PHQ9`        INT,
    `GAD7`        INT,
    `MEQ`         INT,
    PRIMARY KEY (`device_id`) NOT ENFORCED
);

CREATE TABLE IF NOT EXISTS bhdw.ods_sensor_realtime (
    `device_id`        STRING,
    `event_ts`         BIGINT,
    `event_time`       TIMESTAMP(3),
    `heart_rate`       INT,
    `avg_heart_rate`   INT,
    `steps`            INT,
    `wearing`          INT,
    `activity_level`   INT,
    `posture`          STRING,
    PRIMARY KEY (`device_id`, `event_ts`) NOT ENFORCED
);

CREATE TABLE IF NOT EXISTS bhdw.ods_sensor_history (
    `device_id`          STRING,
    `ts_start`           BIGINT,
    `ts_end`             BIGINT,
    `heart_rate_min`     DOUBLE,
    `rmssd`              DOUBLE,
    `sdnn`               DOUBLE,
    `pnn50`              DOUBLE,
    `lf_hf_ratio`        DOUBLE,
    `spo2`               DOUBLE,
    `resp_rate`          DOUBLE,
    `skin_temp`          DOUBLE,
    `steps_min`          INT,
    `activity_level_min` DOUBLE,
    `posture_min`        STRING,
    `wearing_ratio`      DOUBLE,
    `ppg_raw`            ARRAY<DOUBLE>,
    `acc_x_raw`          ARRAY<DOUBLE>,
    `acc_y_raw`          ARRAY<DOUBLE>,
    `acc_z_raw`          ARRAY<DOUBLE>,
    `gyr_x_raw`          ARRAY<DOUBLE>,
    `gyr_y_raw`          ARRAY<DOUBLE>,
    `gyr_z_raw`          ARRAY<DOUBLE>,
    `bia_raw`            ARRAY<DOUBLE>,
    PRIMARY KEY (`device_id`, `ts_start`) NOT ENFORCED
);

-- ============================================================
-- 03  DWD Layer — 明细层
-- ============================================================

-- 实时秒级明细：加心率区间、运动负荷标签
CREATE TABLE IF NOT EXISTS bhdw.dwd_sensor_realtime (
    `device_id`        STRING,
    `event_ts`         BIGINT,
    `event_time`       TIMESTAMP(3),
    `ds`               STRING,          -- yyyy-MM-dd
    `hh`               STRING,          -- HH
    `heart_rate`       INT,
    `avg_heart_rate`   INT,
    `steps`            INT,
    `wearing`          INT,
    `activity_level`   INT,
    `posture`          STRING,
    -- 派生标签
    `hr_zone`          STRING,          -- rest/fat_burn/cardio/peak
    `is_active`        BOOLEAN,         -- activity_level >= 1 且 wearing=1
    PRIMARY KEY (`device_id`, `event_ts`) NOT ENFORCED
);

-- 历史分钟级宽表：加活动强度文本、HRV质量标签
CREATE TABLE IF NOT EXISTS bhdw.dwd_sensor_history_min (
    `device_id`          STRING,
    `ts_start`           BIGINT,
    `ts_end`             BIGINT,
    `event_time`         TIMESTAMP(3),
    `ds`                 STRING,
    `hh`                 STRING,
    `heart_rate_min`     DOUBLE,
    `rmssd`              DOUBLE,
    `sdnn`               DOUBLE,
    `pnn50`              DOUBLE,
    `lf_hf_ratio`        DOUBLE,
    `spo2`               DOUBLE,
    `resp_rate`          DOUBLE,
    `skin_temp`          DOUBLE,
    `steps_min`          INT,
    `activity_level_min` DOUBLE,
    `posture_min`        STRING,
    `wearing_ratio`      DOUBLE,
    -- 派生标签
    `activity_intensity` STRING,        -- sedentary/light/moderate/vigorous
    `hrv_quality`        STRING,        -- excellent/good/fair/poor
    `spo2_status`        STRING,        -- normal/low/critical
    PRIMARY KEY (`device_id`, `ts_start`) NOT ENFORCED
);

-- ============================================================
-- 04  DWS Layer — 汇总层（1小时粒度）
-- ============================================================

CREATE TABLE IF NOT EXISTS bhdw.dws_device_report_1h (
    `device_id`          STRING,
    `ds`                 STRING,
    `hh`                 STRING,
    -- 来自实时流聚合
    `avg_hr_realtime`    DOUBLE,        -- 小时内平均心率（秒级）
    `total_steps_rt`     BIGINT,        -- 小时内累计步数（秒级）
    `active_seconds`     BIGINT,        -- 有效活动秒数
    `wearing_seconds`    BIGINT,        -- 佩戴秒数
    -- 来自历史流聚合
    `avg_rmssd`          DOUBLE,
    `avg_spo2`           DOUBLE,
    `avg_resp_rate`      DOUBLE,
    `avg_skin_temp`      DOUBLE,
    `total_steps_hist`   BIGINT,
    `dominant_posture`   STRING,        -- 小时内主要姿态
    `hrv_quality`        STRING,        -- 小时内HRV质量（众数）
    -- 维度属性
    `user_id`          STRING,
    `sex`              INT,
    `age`              INT,
    `bmi`              DOUBLE,
    `insomnia_level`   STRING,
    `depression_level` STRING,
    `anxiety_level`    STRING,
    `chronotype`       STRING,
    PRIMARY KEY (`device_id`, `ds`, `hh`) NOT ENFORCED
);

-- ============================================================
-- 05  Streaming INSERT — Kafka → ODS
-- ============================================================

INSERT INTO bhdw.ods_user_profile
SELECT device_id, user_id, sex, age, height, weight, ISI, PHQ9, GAD7, MEQ
FROM kafka_user_profile;

INSERT INTO bhdw.ods_sensor_realtime
SELECT
    device_id,
    event_ts,
    event_time,
    heart_rate,
    avg_heart_rate,
    steps,
    wearing,
    activity_level,
    posture
FROM kafka_sensor_realtime;

INSERT INTO bhdw.ods_sensor_history
SELECT
    device_id, ts_start, ts_end,
    heart_rate_min, rmssd, sdnn, pnn50, lf_hf_ratio,
    spo2, resp_rate, skin_temp,
    steps_min, activity_level_min, posture_min, wearing_ratio,
    ppg_raw, acc_x_raw, acc_y_raw, acc_z_raw,
    gyr_x_raw, gyr_y_raw, gyr_z_raw, bia_raw
FROM kafka_sensor_history;

-- ============================================================
-- 06  Streaming INSERT — kafka_user_profile → dim_user
-- ============================================================

INSERT INTO bhdw.dim_user
SELECT
    device_id,
    user_id,
    sex, age, height, weight,
    ROUND(weight / (height / 100.0) / (height / 100.0), 2) AS bmi,
    ISI, PHQ9, GAD7, MEQ,
    CASE
        WHEN ISI <= 7  THEN 'none'
        WHEN ISI <= 14 THEN 'sub-threshold'
        WHEN ISI <= 21 THEN 'moderate'
        ELSE                'severe'
    END AS insomnia_level,
    CASE
        WHEN PHQ9 <= 4  THEN 'minimal'
        WHEN PHQ9 <= 9  THEN 'mild'
        WHEN PHQ9 <= 14 THEN 'moderate'
        WHEN PHQ9 <= 19 THEN 'moderately_severe'
        ELSE                 'severe'
    END AS depression_level,
    CASE
        WHEN GAD7 <= 4  THEN 'minimal'
        WHEN GAD7 <= 9  THEN 'mild'
        WHEN GAD7 <= 14 THEN 'moderate'
        ELSE                 'severe'
    END AS anxiety_level,
    CASE
        WHEN MEQ <= 30 THEN 'definite_evening'
        WHEN MEQ <= 41 THEN 'moderate_evening'
        WHEN MEQ <= 58 THEN 'intermediate'
        WHEN MEQ <= 69 THEN 'moderate_morning'
        ELSE                'definite_morning'
    END AS chronotype
FROM bhdw.ods_user_profile;

-- ============================================================
-- 07  Streaming INSERT — ODS → DWD
-- ============================================================

INSERT INTO bhdw.dwd_sensor_realtime
SELECT
    device_id,
    event_ts,
    event_time,
    DATE_FORMAT(event_time, 'yyyy-MM-dd')   AS ds,
    DATE_FORMAT(event_time, 'HH')           AS hh,
    heart_rate,
    avg_heart_rate,
    steps,
    wearing,
    activity_level,
    posture,
    CASE
        WHEN heart_rate < 60                        THEN 'rest'
        WHEN heart_rate < 100                       THEN 'fat_burn'
        WHEN heart_rate < 140                       THEN 'cardio'
        ELSE                                             'peak'
    END AS hr_zone,
    (activity_level >= 1 AND wearing = 1)          AS is_active
FROM bhdw.ods_sensor_realtime;

INSERT INTO bhdw.dwd_sensor_history_min
SELECT
    device_id,
    ts_start, ts_end,
    TO_TIMESTAMP_LTZ(ts_start, 3)                              AS event_time,
    DATE_FORMAT(TO_TIMESTAMP_LTZ(ts_start, 3), 'yyyy-MM-dd')   AS ds,
    DATE_FORMAT(TO_TIMESTAMP_LTZ(ts_start, 3), 'HH')           AS hh,
    heart_rate_min, rmssd, sdnn, pnn50, lf_hf_ratio,
    spo2, resp_rate, skin_temp,
    steps_min, activity_level_min, posture_min, wearing_ratio,
    CASE
        WHEN activity_level_min < 1.0 THEN 'sedentary'
        WHEN activity_level_min < 2.0 THEN 'light'
        WHEN activity_level_min < 3.0 THEN 'moderate'
        ELSE                               'vigorous'
    END AS activity_intensity,
    CASE
        WHEN wearing_ratio >= 0.9 AND rmssd IS NOT NULL THEN 'excellent'
        WHEN wearing_ratio >= 0.7                       THEN 'good'
        WHEN wearing_ratio >= 0.5                       THEN 'fair'
        ELSE                                                 'poor'
    END AS hrv_quality,
    CASE
        WHEN spo2 >= 95.0 THEN 'normal'
        WHEN spo2 >= 90.0 THEN 'low'
        ELSE                   'critical'
    END AS spo2_status
FROM bhdw.ods_sensor_history;

-- ============================================================
-- 08  Streaming INSERT — DWD → DWS（1小时聚合）
-- ============================================================

INSERT INTO bhdw.dws_device_report_1h
SELECT
    COALESCE(r.device_id, h.device_id)  AS device_id,
    COALESCE(r.ds, h.ds)                AS ds,
    COALESCE(r.hh, h.hh)               AS hh,
    r.avg_hr_realtime,
    r.total_steps_rt,
    r.active_seconds,
    r.wearing_seconds,
    h.avg_rmssd,
    h.avg_spo2,
    h.avg_resp_rate,
    h.avg_skin_temp,
    h.total_steps_hist,
    h.dominant_posture,
    h.hrv_quality,
    -- 维度属性
    u.user_id,
    u.sex,
    u.age,
    u.bmi,
    u.insomnia_level,
    u.depression_level,
    u.anxiety_level,
    u.chronotype
FROM (
    SELECT
        device_id, ds, hh,
        ROUND(AVG(heart_rate), 2)                   AS avg_hr_realtime,
        CAST(MAX(steps) AS BIGINT)                  AS total_steps_rt,
        SUM(CASE WHEN is_active THEN 1 ELSE 0 END)  AS active_seconds,
        SUM(CASE WHEN wearing = 1 THEN 1 ELSE 0 END) AS wearing_seconds
    FROM bhdw.dwd_sensor_realtime
    GROUP BY device_id, ds, hh
) r
FULL OUTER JOIN (
    SELECT
        device_id, ds, hh,
        ROUND(AVG(rmssd), 2)                        AS avg_rmssd,
        ROUND(AVG(spo2), 2)                         AS avg_spo2,
        ROUND(AVG(resp_rate), 2)                    AS avg_resp_rate,
        ROUND(AVG(skin_temp), 2)                    AS avg_skin_temp,
        CAST(SUM(steps_min) AS BIGINT)              AS total_steps_hist,
        -- 取小时内出现次数最多的姿态（近似：取最后一条）
        LAST_VALUE(posture_min)                     AS dominant_posture,
        LAST_VALUE(hrv_quality)                     AS hrv_quality
    FROM bhdw.dwd_sensor_history_min
    GROUP BY device_id, ds, hh
) h
ON r.device_id = h.device_id AND r.ds = h.ds AND r.hh = h.hh
LEFT JOIN bhdw.dim_user u
    ON COALESCE(r.device_id, h.device_id) = u.device_id;
