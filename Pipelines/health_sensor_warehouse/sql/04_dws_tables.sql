-- ============================================================
-- 04_dws_tables.sql — DWS Layer Table Definitions & Loading
-- ============================================================

USE CATALOG paimon_catalog;
USE bhdw;

-- ---- daily_activity_summary --------------------------------
CREATE TABLE IF NOT EXISTS bhdw.dws_daily_activity_summary (
    `device_id`        STRING,
    `ds`               STRING,
    `total_steps`      DOUBLE,
    `total_distance_km` DOUBLE,
    `total_calories`   DOUBLE,
    `active_hours`     INT,
    `avg_hr`           DOUBLE,
    `avg_rmssd`        DOUBLE,
    `record_count`     BIGINT,
    PRIMARY KEY (`device_id`, `ds`) NOT ENFORCED
);

INSERT INTO bhdw.dws_daily_activity_summary
SELECT
    device_id,
    ds,
    SUM(steps)                         AS total_steps,
    ROUND(SUM(distance) / 1000.0, 3)  AS total_distance_km,
    SUM(calories)                      AS total_calories,
    COUNT(DISTINCT hh)                 AS active_hours,
    ROUND(AVG(HR), 2)                  AS avg_hr,
    ROUND(AVG(rmssd), 2)              AS avg_rmssd,
    COUNT(*)                           AS record_count
FROM bhdw.dwd_sensor_hrv_detail
GROUP BY device_id, ds;

-- ---- daily_sleep_summary -----------------------------------
CREATE TABLE IF NOT EXISTS bhdw.dws_daily_sleep_summary (
    `user_id`          STRING,
    `record_date`      DATE,
    `sleep_duration`   DOUBLE,
    `sleep_efficiency` DOUBLE,
    `wakeup_count`     INT,
    `waso_minutes`     DOUBLE,
    `sleep_quality`    STRING,
    `asleep_time`      STRING,
    `wakeup_time`      STRING,
    PRIMARY KEY (`user_id`, `record_date`) NOT ENFORCED
);

INSERT INTO bhdw.dws_daily_sleep_summary
SELECT
    user_id,
    record_date,
    sleep_duration,
    sleep_efficiency,
    wakeup_at_night    AS wakeup_count,
    waso               AS waso_minutes,
    sleep_quality,
    asleep             AS asleep_time,
    wakeup             AS wakeup_time
FROM bhdw.dwd_sleep_detail;

-- ---- participant_health_profile ----------------------------
CREATE TABLE IF NOT EXISTS bhdw.dws_participant_health_profile (
    `device_id`            STRING,
    `avg_daily_steps`      DOUBLE,
    `avg_sleep_duration`   DOUBLE,
    `avg_sleep_efficiency` DOUBLE,
    `avg_hr`               DOUBLE,
    `avg_rmssd`            DOUBLE,
    `total_days_tracked`   BIGINT,
    `exercise_frequency`   INT,
    `insomnia_level`       STRING,
    `depression_level`     STRING,
    `anxiety_level`        STRING,
    `chronotype`           STRING,
    `bmi`                  DOUBLE,
    PRIMARY KEY (`device_id`) NOT ENFORCED
);

INSERT INTO bhdw.dws_participant_health_profile
SELECT
    p.device_id,
    ROUND(a.avg_daily_steps, 2)      AS avg_daily_steps,
    ROUND(s.avg_sleep_duration, 2)   AS avg_sleep_duration,
    ROUND(s.avg_sleep_efficiency, 4) AS avg_sleep_efficiency,
    ROUND(a.avg_hr, 2)               AS avg_hr,
    ROUND(a.avg_rmssd, 2)            AS avg_rmssd,
    a.total_days_tracked,
    p.exercise                       AS exercise_frequency,
    p.insomnia_level,
    p.depression_level,
    p.anxiety_level,
    p.chronotype,
    p.bmi
FROM bhdw.dwd_dim_participant p
LEFT JOIN (
    SELECT
        device_id,
        AVG(total_steps) AS avg_daily_steps,
        AVG(avg_hr)      AS avg_hr,
        AVG(avg_rmssd)   AS avg_rmssd,
        COUNT(*)         AS total_days_tracked
    FROM bhdw.dws_daily_activity_summary
    GROUP BY device_id
) a ON p.device_id = a.device_id
LEFT JOIN (
    SELECT
        user_id,
        AVG(sleep_duration)   AS avg_sleep_duration,
        AVG(sleep_efficiency) AS avg_sleep_efficiency
    FROM bhdw.dws_daily_sleep_summary
    GROUP BY user_id
) s ON p.device_id = s.user_id;
