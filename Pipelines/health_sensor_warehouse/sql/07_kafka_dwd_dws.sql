-- ============================================================
-- 07_kafka_dwd_dws.sql — Streaming: DWD/DWS for raw sensor
-- 基于 sensor_raw_event 做实时聚合
-- 运行模式：STREAMING
-- ============================================================

SET 'execution.runtime-mode' = 'streaming';
SET 'execution.checkpointing.interval' = '1min';
SET 'table.exec.sink.not-null-enforcer' = 'DROP';
SET 'table.exec.sink.upsert-materialize' = 'NONE';

USE CATALOG paimon_catalog;
USE bhdw;

-- ============================================================
-- DWD: 按传感器类型拆分为明细表
-- ============================================================

-- ---- DWD: 心率明细 -----------------------------------------
CREATE TABLE IF NOT EXISTS bhdw.dwd_sensor_hrm (
    `device_id`   STRING,
    `event_ts`    BIGINT,
    `event_time`  TIMESTAMP(3),
    `ds`          STRING,
    `hh`          STRING,
    `HR`          DOUBLE,
    PRIMARY KEY (`device_id`, `event_ts`) NOT ENFORCED
);

-- ---- DWD: 加速度计明细 -------------------------------------
CREATE TABLE IF NOT EXISTS bhdw.dwd_sensor_acc (
    `device_id`   STRING,
    `event_ts`    BIGINT,
    `event_time`  TIMESTAMP(3),
    `ds`          STRING,
    `hh`          STRING,
    `x`           DOUBLE,
    `y`           DOUBLE,
    `z`           DOUBLE,
    `magnitude`   DOUBLE,
    PRIMARY KEY (`device_id`, `event_ts`) NOT ENFORCED
);

-- ---- DWD: 计步器明细 ---------------------------------------
CREATE TABLE IF NOT EXISTS bhdw.dwd_sensor_ped (
    `device_id`      STRING,
    `event_ts`       BIGINT,
    `event_time`     TIMESTAMP(3),
    `ds`             STRING,
    `hh`             STRING,
    `steps`          INT,
    `steps_walking`  INT,
    `steps_running`  INT,
    `distance`       DOUBLE,
    `calories`       DOUBLE,
    PRIMARY KEY (`device_id`, `event_ts`) NOT ENFORCED
);

-- ---- DWD: 光照明细 -----------------------------------------
CREATE TABLE IF NOT EXISTS bhdw.dwd_sensor_lit (
    `device_id`              STRING,
    `event_ts`               BIGINT,
    `event_time`             TIMESTAMP(3),
    `ds`                     STRING,
    `hh`                     STRING,
    `ambient_light_intensity` DOUBLE,
    PRIMARY KEY (`device_id`, `event_ts`) NOT ENFORCED
);

-- ---- 流式写入 DWD（STATEMENT SET 并行写入）-----------------
EXECUTE STATEMENT SET
BEGIN

    INSERT INTO bhdw.dwd_sensor_hrm
    SELECT device_id, event_ts, event_time, ds, hh, HR
    FROM bhdw.ods_sensor_raw_event
    WHERE sensor_type = 'hrm';

    INSERT INTO bhdw.dwd_sensor_acc
    SELECT device_id, event_ts, event_time, ds, hh,
           x, y, z,
           SQRT(x * x + y * y + z * z) AS magnitude
    FROM bhdw.ods_sensor_raw_event
    WHERE sensor_type = 'acc';

    INSERT INTO bhdw.dwd_sensor_ped
    SELECT device_id, event_ts, event_time, ds, hh,
           steps, steps_walking, steps_running, distance, calories
    FROM bhdw.ods_sensor_raw_event
    WHERE sensor_type = 'ped';

    INSERT INTO bhdw.dwd_sensor_lit
    SELECT device_id, event_ts, event_time, ds, hh,
           ambient_light_intensity
    FROM bhdw.ods_sensor_raw_event
    WHERE sensor_type = 'lit';

END;

-- ============================================================
-- DWS: 实时每小时心率汇总（窗口聚合）
-- ============================================================

CREATE TABLE IF NOT EXISTS bhdw.dws_hourly_hr_summary (
    `device_id`    STRING,
    `window_start` TIMESTAMP(3),
    `window_end`   TIMESTAMP(3),
    `ds`           STRING,
    `hh`           STRING,
    `avg_hr`       DOUBLE,
    `min_hr`       DOUBLE,
    `max_hr`       DOUBLE,
    `record_count` BIGINT,
    PRIMARY KEY (`device_id`, `window_start`) NOT ENFORCED
);

-- 需要单独提交（不能和上面 STATEMENT SET 混合）
INSERT INTO bhdw.dws_hourly_hr_summary
SELECT
    device_id,
    window_start,
    window_end,
    DATE_FORMAT(window_start, 'yyyy-MM-dd') AS ds,
    DATE_FORMAT(window_start, 'HH')         AS hh,
    ROUND(AVG(HR), 2)                       AS avg_hr,
    ROUND(MIN(HR), 2)                       AS min_hr,
    ROUND(MAX(HR), 2)                       AS max_hr,
    COUNT(*)                                AS record_count
FROM TABLE(
    TUMBLE(TABLE bhdw.dwd_sensor_hrm, DESCRIPTOR(event_time), INTERVAL '1' HOUR)
)
GROUP BY device_id, window_start, window_end;
