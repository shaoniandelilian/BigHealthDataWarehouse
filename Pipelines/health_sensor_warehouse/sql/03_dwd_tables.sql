-- ============================================================
-- 03_dwd_tables.sql — DWD Layer Table Definitions & Loading
-- ============================================================

USE CATALOG paimon_catalog;
USE bhdw;

-- ---- dim_participant: participant dimension -----------------
CREATE TABLE IF NOT EXISTS bhdw.dwd_dim_participant (
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

INSERT INTO bhdw.dwd_dim_participant
SELECT
    device_id,
    sex,
    age,
    marriage,
    occupation,
    smartwatch,
    regular,
    exercise,
    coffee,
    smoking,
    drinking,
    height,
    weight,
    -- BMI = weight(kg) / height(m)^2
    ROUND(weight / (height / 100.0) / (height / 100.0), 2) AS bmi,
    ISI_1,
    PHQ9_1,
    GAD7_1,
    MEQ,
    ISI_2,
    PHQ9_2,
    GAD7_2,
    ISI_F,
    PHQ9_F,
    GAD7_F,
    -- ISI insomnia severity: 0-7 none, 8-14 sub-threshold, 15-21 moderate, 22-28 severe
    CASE
        WHEN ISI_1 <= 7  THEN 'none'
        WHEN ISI_1 <= 14 THEN 'sub-threshold'
        WHEN ISI_1 <= 21 THEN 'moderate'
        ELSE 'severe'
    END AS insomnia_level,
    -- PHQ-9 depression: 0-4 minimal, 5-9 mild, 10-14 moderate, 15-19 mod-severe, 20-27 severe
    CASE
        WHEN PHQ9_1 <= 4  THEN 'minimal'
        WHEN PHQ9_1 <= 9  THEN 'mild'
        WHEN PHQ9_1 <= 14 THEN 'moderate'
        WHEN PHQ9_1 <= 19 THEN 'moderately_severe'
        ELSE 'severe'
    END AS depression_level,
    -- GAD-7 anxiety: 0-4 minimal, 5-9 mild, 10-14 moderate, 15-21 severe
    CASE
        WHEN GAD7_1 <= 4  THEN 'minimal'
        WHEN GAD7_1 <= 9  THEN 'mild'
        WHEN GAD7_1 <= 14 THEN 'moderate'
        ELSE 'severe'
    END AS anxiety_level,
    -- MEQ chronotype: 16-30 definite evening, 31-41 moderate evening, 42-58 intermediate, 59-69 moderate morning, 70-86 definite morning
    CASE
        WHEN MEQ <= 30 THEN 'definite_evening'
        WHEN MEQ <= 41 THEN 'moderate_evening'
        WHEN MEQ <= 58 THEN 'intermediate'
        WHEN MEQ <= 69 THEN 'moderate_morning'
        ELSE 'definite_morning'
    END AS chronotype
FROM bhdw.ods_survey;

-- ---- sleep_detail: enriched sleep diary --------------------
CREATE TABLE IF NOT EXISTS bhdw.dwd_sleep_detail (
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

INSERT INTO bhdw.dwd_sleep_detail
SELECT
    user_id,
    record_date,
    go2bed,
    asleep,
    wakeup,
    wakeup_at_night,
    waso,
    sleep_duration,
    in_bed_duration,
    sleep_latency,
    sleep_efficiency,
    -- sleep quality: good (efficiency >= 0.85 and duration 7-9h), fair, poor
    CASE
        WHEN sleep_efficiency >= 0.85 AND sleep_duration >= 7.0 AND sleep_duration <= 9.0 THEN 'good'
        WHEN sleep_efficiency >= 0.75 AND sleep_duration >= 6.0 THEN 'fair'
        ELSE 'poor'
    END AS sleep_quality,
    -- is_late_sleep: asleep time > 01:00 (comparing HH:MM:SS string)
    CASE
        WHEN asleep > '01:00:00' AND asleep <= '12:00:00' THEN TRUE
        ELSE FALSE
    END AS is_late_sleep
FROM bhdw.ods_sleep_diary;

-- ---- sensor_hrv_detail: enriched HRV sensor data -----------
CREATE TABLE IF NOT EXISTS bhdw.dwd_sensor_hrv_detail (
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

INSERT INTO bhdw.dwd_sensor_hrv_detail
SELECT
    device_id,
    ts_start,
    ts_end,
    -- convert epoch millis to TIMESTAMP
    TO_TIMESTAMP_LTZ(ts_start, 3) AS event_time,
    DATE_FORMAT(TO_TIMESTAMP_LTZ(ts_start, 3), 'yyyy-MM-dd') AS ds,
    DATE_FORMAT(TO_TIMESTAMP_LTZ(ts_start, 3), 'HH') AS hh,
    missingness_score,
    HR,
    ibi,
    acc_x_avg,
    acc_y_avg,
    acc_z_avg,
    grv_x_avg,
    grv_y_avg,
    grv_z_avg,
    grv_w_avg,
    gyr_x_avg,
    gyr_y_avg,
    gyr_z_avg,
    steps,
    distance,
    calories,
    light_avg,
    sdnn,
    sdsd,
    rmssd,
    pnn20,
    pnn50,
    lf,
    hf,
    lf_hf_ratio,
    -- activity intensity based on accelerometer magnitude: sqrt(x^2+y^2+z^2)
    CASE
        WHEN SQRT(acc_x_avg * acc_x_avg + acc_y_avg * acc_y_avg + acc_z_avg * acc_z_avg) < 1.5 THEN 'sedentary'
        WHEN SQRT(acc_x_avg * acc_x_avg + acc_y_avg * acc_y_avg + acc_z_avg * acc_z_avg) < 5.0 THEN 'light'
        WHEN SQRT(acc_x_avg * acc_x_avg + acc_y_avg * acc_y_avg + acc_z_avg * acc_z_avg) < 10.0 THEN 'moderate'
        ELSE 'vigorous'
    END AS activity_intensity,
    -- HRV data quality based on missingness score
    CASE
        WHEN missingness_score <= 0.1  THEN 'excellent'
        WHEN missingness_score <= 0.3  THEN 'good'
        WHEN missingness_score <= 0.5  THEN 'fair'
        ELSE 'poor'
    END AS hrv_quality
FROM bhdw.ods_sensor_hrv;
