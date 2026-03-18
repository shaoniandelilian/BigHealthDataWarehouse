from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

default_args = {
    "owner": "airflow",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="fluss_enriched_orders_snapshot",
    default_args=default_args,
    start_date=datetime(2024, 1, 1),
    schedule="*/1 * * * *",
    catchup=False,
    tags=["flink", "batch", "fluss", "paimon"],
) as dag:

    run_flink_sql = BashOperator(
        task_id="snapshot_enriched_orders",
        append_env=True,
        bash_command="""
        set -e
        set -o pipefail

        /opt/flink/bin/sql-client.sh <<'SQL' 2>&1 | tee /tmp/flink_sql_run.log
SET 'execution.runtime-mode' = 'BATCH';
SET 'table.dml-sync' = 'true';

CREATE CATALOG fluss_catalog WITH (
    'type' = 'fluss',
    'bootstrap.servers' = 'fluss-coordinator:9123',
    'paimon.s3.access-key' = 'minioadmin',
    'paimon.s3.secret-key' = 'minioadmin'
);

USE CATALOG fluss_catalog;

CREATE TABLE IF NOT EXISTS datalake_enriched_orders_ts (
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
    `snapshot_ts` TIMESTAMP(3),
    PRIMARY KEY (`order_key`, `snapshot_ts`) NOT ENFORCED
) WITH (
    'table.datalake.enabled' = 'true'
);

INSERT INTO datalake_enriched_orders_ts
SELECT `order_key`,
       `cust_key`,
       `total_price`,
       `order_date`,
       `order_priority`,
       `clerk`,
       `cust_name`,
       `cust_phone`,
       `cust_acctbal`,
       `cust_mktsegment`,
       `nation_name`,
       CAST(CURRENT_TIMESTAMP AS TIMESTAMP(3)) AS snapshot_ts
FROM datalake_enriched_orders;
SQL

        if grep -q '\\[ERROR\\]' /tmp/flink_sql_run.log; then
            echo "Flink SQL execution failed!"
            exit 1
        fi

        echo "Flink SQL execution succeeded."
        """,
    )
