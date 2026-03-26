-- ============================================================
-- 01_ods_tables.sql — ODS Layer Table Definitions
-- ============================================================

USE CATALOG paimon_catalog;
USE bhdw;

-- Survey: participant questionnaire (49 rows)
CREATE TABLE IF NOT EXISTS bhdw.ods_survey (
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

-- Sleep diary (1,373 rows)
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

-- Sensor HRV 5-min aggregated (38,914 rows, filtered)
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
