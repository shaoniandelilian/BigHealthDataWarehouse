from airflow import DAG
from airflow.providers.ssh.operators.ssh import SSHOperator
from datetime import datetime, timedelta

# 1. 基础配置
default_args = {
    'owner': 'lakehouse_team',
    'depends_on_past': False,
    'start_date': datetime(2026, 3, 27),
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

# 从 Airflow 原生的 Variables（变量管理库）动态获取敏感凭证，避免明文上传到 Git
from airflow.models import Variable
S3_ACCESS_KEY = Variable.get("paimon_s3_access_key", default_var="{{ PAIMON_S3_AK }}")
S3_SECRET_KEY = Variable.get("paimon_s3_secret_key", default_var="{{ PAIMON_S3_SK }}")
MYSQL_PWD = Variable.get("mysql_lakehouse_pwd", default_var="{{ MYSQL_PWD }}")

# 2. 将 Flink SQL 脚本直接作为长字符串内嵌在 Python 文件中
FLINK_SQL_CONTENT = f"""
-- 声明批处理模式
SET 'execution.runtime-mode' = 'batch';

-- 构建 Paimon 目录环境
CREATE CATALOG IF NOT EXISTS paimon_catalog WITH (
  'type' = 'paimon',
  'warehouse' = 's3://fluss/paimon',
  's3.endpoint' = 'https://oss-cn-hangzhou-internal.aliyuncs.com',
  's3.access-key' = '{S3_ACCESS_KEY}',
  's3.secret-key' = '{S3_SECRET_KEY}'
);
USE CATALOG paimon_catalog;

-- ====== 维度表 1: base_province ======
CREATE TEMPORARY TABLE mysql_base_province (
  id BIGINT,
  name STRING,
  region_id STRING,
  area_code STRING,
  iso_code STRING,
  iso_3166_2 STRING
) WITH (
  'connector' = 'jdbc',
  'url' = 'jdbc:mysql://mysql:3306/laife_mock_stream',
  'table-name' = 'base_province',
  'username' = 'root',
  'password' = '{MYSQL_PWD}'
);

INSERT OVERWRITE laife_stream.ods_base_province 
SELECT * FROM mysql_base_province;

-- ====== 维度表 2: base_category1 ======
CREATE TEMPORARY TABLE mysql_base_category1 (
  id BIGINT,
  name STRING
) WITH (
  'connector' = 'jdbc',
  'url' = 'jdbc:mysql://mysql:3306/laife_mock_stream',
  'table-name' = 'base_category1',
  'username' = 'root',
  'password' = '{MYSQL_PWD}'
);

INSERT OVERWRITE laife_stream.ods_base_category1 
SELECT * FROM mysql_base_category1;
"""


with DAG(
    'daily_paimon_dim_sync_dag',
    default_args=default_args,
    schedule_interval='30 2 * * *', 
    catchup=False,
    tags=['ods', 'dim', 'flink']
) as dag:

    # 3. 核心节点：通过 SSH 远程连入装有 kubectl 的 K8s 宿主服务器执行命令
    run_flink_batch_job = SSHOperator(
        task_id='execute_dim_sync_sql',
        ssh_conn_id='k8s_master_ssh',  # 这里填你在 Airflow 网页后台配置好的连接 ID
        command=f"""
        # 远程宿主机接收到这个超长命令后，会投递给 Flink 容器去执行
        kubectl exec -i -n lakehouse deployment/flink-jobmanager -- bash -c 'cat > /tmp/airflow_dim_sync.sql && /opt/flink/bin/sql-client.sh -f /tmp/airflow_dim_sync.sql' << 'EOF_SQL'
{FLINK_SQL_CONTENT}
EOF_SQL
        """
    )
