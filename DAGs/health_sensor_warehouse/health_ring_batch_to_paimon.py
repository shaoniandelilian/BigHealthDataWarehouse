from __future__ import annotations

import pendulum
from datetime import timedelta

from airflow.decorators import dag, task


default_args = {
    "owner": "airflow",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}


@dag(
    dag_id="health_ring_batch_to_paimon",
    default_args=default_args,
    start_date=pendulum.datetime(2024, 1, 1, tz="UTC"),
    schedule="@once",
    catchup=False,
    tags=["flink", "batch", "paimon", "health_ring"],
)
def health_ring_batch_to_paimon():
    """
    Health Ring 离线批量数据管道：CSV → Paimon ODS → DWD → DWS
    执行顺序：catalog → ods_tables → csv_to_ods → dwd_tables → dws_tables
    """

    FLINK_SQL_CLIENT = "/opt/flink/bin/sql-client.sh"

    def _flink_sql_task(sql: str, log_file: str) -> str:
        """生成 Flink SQL Client bash 命令模板"""
        return rf"""
        set -e
        set -o pipefail

        {FLINK_SQL_CLIENT} <<'SQL' 2>&1 | tee {log_file}
{sql}
SQL

        if grep -q '\[ERROR\]' {log_file}; then
            echo "Flink SQL execution failed! Check {log_file}"
            exit 1
        fi

        echo "Flink SQL execution succeeded."
        """

    # ---- Step 1: Catalog & Database 初始化 --------------------
    @task.bash(append_env=True)
    def init_catalog() -> str:
        return _flink_sql_task(
            sql="""\
SET 'execution.runtime-mode' = 'batch';
SET 'table.dml-sync' = 'true';
SET 'table.exec.sink.not-null-enforcer' = 'DROP';
SET 'table.exec.sink.upsert-materialize' = 'NONE';
SET 'parallelism.default' = '1';

CREATE CATALOG paimon_catalog WITH (
    'type' = 'paimon',
    'warehouse' = 's3://fluss/paimon',
    's3.endpoint' = '<your-endpoint>',
    's3.access-key' = '<your-access-key>',
    's3.secret-key' = '<your-secret-key>',
    's3.path.style.access' = 'false'
);

USE CATALOG paimon_catalog;

CREATE DATABASE IF NOT EXISTS bhdw_ods;
CREATE DATABASE IF NOT EXISTS bhdw_dwd;
CREATE DATABASE IF NOT EXISTS bhdw_dws;""",
            log_file="/tmp/health_ring_00_catalog.log",
        )

    # ---- Step 2: ODS 建表 ------------------------------------
    @task.bash(append_env=True)
    def create_ods_tables() -> str:
        return _flink_sql_task(
            sql="""\
SET 'execution.runtime-mode' = 'batch';
SET 'table.dml-sync' = 'true';

CREATE CATALOG paimon_catalog WITH (
    'type' = 'paimon',
    'warehouse' = 's3://fluss/paimon',
    's3.endpoint' = '<your-endpoint>',
    's3.access-key' = '<your-access-key>',
    's3.secret-key' = '<your-secret-key>',
    's3.path.style.access' = 'false'
);

USE CATALOG paimon_catalog;

CREATE TABLE IF NOT EXISTS bhdw_ods.survey (
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

CREATE TABLE IF NOT EXISTS bhdw_ods.sleep_diary (
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

CREATE TABLE IF NOT EXISTS bhdw_ods.sensor_hrv (
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
);""",
            log_file="/tmp/health_ring_01_ods_tables.log",
        )

    # ---- Step 3: CSV → ODS -----------------------------------
    @task.bash(append_env=True)
    def csv_to_ods() -> str:
        return _flink_sql_task(
            sql="""\
SET 'execution.runtime-mode' = 'batch';
SET 'table.dml-sync' = 'true';
SET 'table.exec.sink.not-null-enforcer' = 'DROP';
SET 'table.exec.sink.upsert-materialize' = 'NONE';
SET 'parallelism.default' = '1';

CREATE CATALOG paimon_catalog WITH (
    'type' = 'paimon',
    'warehouse' = 's3://fluss/paimon',
    's3.endpoint' = '<your-endpoint>',
    's3.access-key' = '<your-access-key>',
    's3.secret-key' = '<your-secret-key>',
    's3.path.style.access' = 'false'
);

USE CATALOG paimon_catalog;

CREATE TEMPORARY TABLE csv_survey (
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
    'connector' = 'filesystem',
    'path' = '/data/28509740/survey.csv',
    'format' = 'csv',
    'csv.ignore-parse-errors' = 'true',
    'csv.allow-comments' = 'true'
);

INSERT INTO bhdw_ods.survey SELECT * FROM csv_survey;

CREATE TEMPORARY TABLE csv_sleep_diary (
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
    `sleep_efficiency` DOUBLE
) WITH (
    'connector' = 'filesystem',
    'path' = '/data/28509740/sleep_diary.csv',
    'format' = 'csv',
    'csv.ignore-parse-errors' = 'true',
    'csv.allow-comments' = 'true'
);

INSERT INTO bhdw_ods.sleep_diary SELECT * FROM csv_sleep_diary;

CREATE TEMPORARY TABLE csv_sensor_hrv (
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
    `lf_hf_ratio`      DOUBLE
) WITH (
    'connector' = 'filesystem',
    'path' = '/data/28509740/sensor_hrv_filtered.csv',
    'format' = 'csv',
    'csv.ignore-parse-errors' = 'true',
    'csv.allow-comments' = 'true'
);

INSERT INTO bhdw_ods.sensor_hrv SELECT * FROM csv_sensor_hrv;""",
            log_file="/tmp/health_ring_02_csv_to_ods.log",
        )

    # ---- Step 4: ODS → DWD ----------------------------------
    @task.bash(append_env=True)
    def ods_to_dwd() -> str:
        return _flink_sql_task(
            sql="""\
SET 'execution.runtime-mode' = 'batch';
SET 'table.dml-sync' = 'true';
SET 'table.exec.sink.not-null-enforcer' = 'DROP';
SET 'table.exec.sink.upsert-materialize' = 'NONE';
SET 'parallelism.default' = '1';

CREATE CATALOG paimon_catalog WITH (
    'type' = 'paimon',
    'warehouse' = 's3://fluss/paimon',
    's3.endpoint' = '<your-endpoint>',
    's3.access-key' = '<your-access-key>',
    's3.secret-key' = '<your-secret-key>',
    's3.path.style.access' = 'false'
);

USE CATALOG paimon_catalog;

CREATE TABLE IF NOT EXISTS bhdw_dwd.dim_participant (
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

INSERT INTO bhdw_dwd.dim_participant
SELECT
    device_id, sex, age, marriage, occupation, smartwatch, regular,
    exercise, coffee, smoking, drinking, height, weight,
    ROUND(weight / (height / 100.0) / (height / 100.0), 2) AS bmi,
    ISI_1, PHQ9_1, GAD7_1, MEQ, ISI_2, PHQ9_2, GAD7_2, ISI_F, PHQ9_F, GAD7_F,
    CASE
        WHEN ISI_1 <= 7  THEN 'none'
        WHEN ISI_1 <= 14 THEN 'sub-threshold'
        WHEN ISI_1 <= 21 THEN 'moderate'
        ELSE 'severe'
    END,
    CASE
        WHEN PHQ9_1 <= 4  THEN 'minimal'
        WHEN PHQ9_1 <= 9  THEN 'mild'
        WHEN PHQ9_1 <= 14 THEN 'moderate'
        WHEN PHQ9_1 <= 19 THEN 'moderately_severe'
        ELSE 'severe'
    END,
    CASE
        WHEN GAD7_1 <= 4  THEN 'minimal'
        WHEN GAD7_1 <= 9  THEN 'mild'
        WHEN GAD7_1 <= 14 THEN 'moderate'
        ELSE 'severe'
    END,
    CASE
        WHEN MEQ <= 30 THEN 'definite_evening'
        WHEN MEQ <= 41 THEN 'moderate_evening'
        WHEN MEQ <= 58 THEN 'intermediate'
        WHEN MEQ <= 69 THEN 'moderate_morning'
        ELSE 'definite_morning'
    END
FROM bhdw_ods.survey;

CREATE TABLE IF NOT EXISTS bhdw_dwd.sleep_detail (
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

INSERT INTO bhdw_dwd.sleep_detail
SELECT
    user_id, record_date, go2bed, asleep, wakeup,
    wakeup_at_night, waso, sleep_duration, in_bed_duration,
    sleep_latency, sleep_efficiency,
    CASE
        WHEN sleep_efficiency >= 0.85 AND sleep_duration >= 7.0 AND sleep_duration <= 9.0 THEN 'good'
        WHEN sleep_efficiency >= 0.75 AND sleep_duration >= 6.0 THEN 'fair'
        ELSE 'poor'
    END,
    CASE
        WHEN asleep > '01:00:00' AND asleep <= '12:00:00' THEN TRUE
        ELSE FALSE
    END
FROM bhdw_ods.sleep_diary;

CREATE TABLE IF NOT EXISTS bhdw_dwd.sensor_hrv_detail (
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

INSERT INTO bhdw_dwd.sensor_hrv_detail
SELECT
    device_id, ts_start, ts_end,
    TO_TIMESTAMP_LTZ(ts_start, 3),
    DATE_FORMAT(TO_TIMESTAMP_LTZ(ts_start, 3), 'yyyy-MM-dd'),
    DATE_FORMAT(TO_TIMESTAMP_LTZ(ts_start, 3), 'HH'),
    missingness_score, HR, ibi,
    acc_x_avg, acc_y_avg, acc_z_avg,
    grv_x_avg, grv_y_avg, grv_z_avg, grv_w_avg,
    gyr_x_avg, gyr_y_avg, gyr_z_avg,
    steps, distance, calories, light_avg,
    sdnn, sdsd, rmssd, pnn20, pnn50, lf, hf, lf_hf_ratio,
    CASE
        WHEN SQRT(acc_x_avg * acc_x_avg + acc_y_avg * acc_y_avg + acc_z_avg * acc_z_avg) < 1.5 THEN 'sedentary'
        WHEN SQRT(acc_x_avg * acc_x_avg + acc_y_avg * acc_y_avg + acc_z_avg * acc_z_avg) < 5.0 THEN 'light'
        WHEN SQRT(acc_x_avg * acc_x_avg + acc_y_avg * acc_y_avg + acc_z_avg * acc_z_avg) < 10.0 THEN 'moderate'
        ELSE 'vigorous'
    END,
    CASE
        WHEN missingness_score <= 0.1  THEN 'excellent'
        WHEN missingness_score <= 0.3  THEN 'good'
        WHEN missingness_score <= 0.5  THEN 'fair'
        ELSE 'poor'
    END
FROM bhdw_ods.sensor_hrv;""",
            log_file="/tmp/health_ring_03_dwd.log",
        )

    # ---- Step 5: DWD → DWS ----------------------------------
    @task.bash(append_env=True)
    def dwd_to_dws() -> str:
        return _flink_sql_task(
            sql="""\
SET 'execution.runtime-mode' = 'batch';
SET 'table.dml-sync' = 'true';
SET 'table.exec.sink.not-null-enforcer' = 'DROP';
SET 'table.exec.sink.upsert-materialize' = 'NONE';
SET 'parallelism.default' = '1';

CREATE CATALOG paimon_catalog WITH (
    'type' = 'paimon',
    'warehouse' = 's3://fluss/paimon',
    's3.endpoint' = '<your-endpoint>',
    's3.access-key' = '<your-access-key>',
    's3.secret-key' = '<your-secret-key>',
    's3.path.style.access' = 'false'
);

USE CATALOG paimon_catalog;

CREATE TABLE IF NOT EXISTS bhdw_dws.daily_activity_summary (
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

INSERT INTO bhdw_dws.daily_activity_summary
SELECT
    device_id, ds,
    SUM(steps),
    ROUND(SUM(distance) / 1000.0, 3),
    SUM(calories),
    COUNT(DISTINCT hh),
    ROUND(AVG(HR), 2),
    ROUND(AVG(rmssd), 2),
    COUNT(*)
FROM bhdw_dwd.sensor_hrv_detail
GROUP BY device_id, ds;

CREATE TABLE IF NOT EXISTS bhdw_dws.daily_sleep_summary (
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

INSERT INTO bhdw_dws.daily_sleep_summary
SELECT
    user_id, record_date, sleep_duration, sleep_efficiency,
    wakeup_at_night, waso, sleep_quality, asleep, wakeup
FROM bhdw_dwd.sleep_detail;

CREATE TABLE IF NOT EXISTS bhdw_dws.participant_health_profile (
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

INSERT INTO bhdw_dws.participant_health_profile
SELECT
    p.device_id,
    ROUND(a.avg_daily_steps, 2),
    ROUND(s.avg_sleep_duration, 2),
    ROUND(s.avg_sleep_efficiency, 4),
    ROUND(a.avg_hr, 2),
    ROUND(a.avg_rmssd, 2),
    a.total_days_tracked,
    p.exercise,
    p.insomnia_level,
    p.depression_level,
    p.anxiety_level,
    p.chronotype,
    p.bmi
FROM bhdw_dwd.dim_participant p
LEFT JOIN (
    SELECT
        device_id,
        AVG(total_steps) AS avg_daily_steps,
        AVG(avg_hr)      AS avg_hr,
        AVG(avg_rmssd)   AS avg_rmssd,
        COUNT(*)         AS total_days_tracked
    FROM bhdw_dws.daily_activity_summary
    GROUP BY device_id
) a ON p.device_id = a.device_id
LEFT JOIN (
    SELECT
        user_id,
        AVG(sleep_duration)   AS avg_sleep_duration,
        AVG(sleep_efficiency) AS avg_sleep_efficiency
    FROM bhdw_dws.daily_sleep_summary
    GROUP BY user_id
) s ON p.device_id = s.user_id;""",
            log_file="/tmp/health_ring_04_dws.log",
        )

    # ---- DAG 依赖链 ------------------------------------------
    t1 = init_catalog()
    t2 = create_ods_tables()
    t3 = csv_to_ods()
    t4 = ods_to_dwd()
    t5 = dwd_to_dws()

    t1 >> t2 >> t3 >> t4 >> t5


health_ring_batch_to_paimon()
