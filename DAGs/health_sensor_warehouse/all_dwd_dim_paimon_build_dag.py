from airflow import DAG
from airflow.providers.ssh.operators.ssh import SSHOperator
from datetime import datetime, timedelta
from airflow.models import Variable

# 1. 基础配置
default_args = {
    'owner': 'lakehouse_team',
    'depends_on_past': False,
    'start_date': datetime(2026, 3, 27),
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

S3_ACCESS_KEY = Variable.get("paimon_s3_access_key")
S3_SECRET_KEY = Variable.get("paimon_s3_secret_key")

# 2. 核心 DWD 层与 DIM 层打宽清洗：全量整合版 SQL
# 包含了文档设计的所有 10 张大宽表
FLINK_SQL_CONTENT = f"""
SET 'execution.runtime-mode' = 'batch';

CREATE CATALOG IF NOT EXISTS paimon_catalog WITH (
  'type' = 'paimon',
  'warehouse' = 's3://fluss/paimon',
  's3.endpoint' = 'https://oss-cn-hangzhou-internal.aliyuncs.com',
  's3.access-key' = '{S3_ACCESS_KEY}',
  's3.secret-key' = '{S3_SECRET_KEY}'
);
USE CATALOG paimon_catalog;

-- =========================================
-- 模块一：核心商品维度表 (dim_sku_info)
-- =========================================
CREATE TABLE IF NOT EXISTS laife_stream.dim_sku_info (
    id BIGINT, spu_id BIGINT, price DECIMAL(16, 2), sku_name STRING, sku_desc STRING,
    weight DECIMAL(16, 2), tm_id BIGINT, tm_name STRING, category3_id BIGINT, category3_name STRING,
    category2_id BIGINT, category2_name STRING, category1_id BIGINT, category1_name STRING,
    spu_name STRING, create_time TIMESTAMP(3),
    PRIMARY KEY (id) NOT ENFORCED
);
INSERT OVERWRITE laife_stream.dim_sku_info
SELECT sku.id, sku.spu_id, sku.price, sku.sku_name, sku.sku_desc, sku.weight, sku.tm_id, tm.tm_name,
       sku.category3_id, c3.name AS category3_name, c3.category2_id, c2.name AS category2_name,
       c2.category1_id, c1.name AS category1_name, spu.spu_name, sku.create_time
FROM laife_stream.ods_sku_info sku
LEFT JOIN laife_stream.ods_spu_info spu ON sku.spu_id = spu.id
LEFT JOIN laife_stream.ods_base_trademark tm ON sku.tm_id = tm.id
LEFT JOIN laife_stream.ods_base_category3 c3 ON sku.category3_id = c3.id
LEFT JOIN laife_stream.ods_base_category2 c2 ON c3.category2_id = c2.id
LEFT JOIN laife_stream.ods_base_category1 c1 ON c2.category1_id = c1.id;

-- =========================================
-- 模块二：核心交易明细事实表 (dwd_trade_order_detail)
-- =========================================
CREATE TABLE IF NOT EXISTS laife_stream.dwd_trade_order_detail (
    id BIGINT, order_id BIGINT, user_id BIGINT, sku_id BIGINT, province_id BIGINT, source_type STRING,
    order_price DECIMAL(16, 2), sku_num BIGINT, split_original_amount DECIMAL(16, 2),
    split_activity_amount DECIMAL(16, 2), split_coupon_amount DECIMAL(16, 2),
    split_total_amount DECIMAL(16, 2), order_status STRING, create_time TIMESTAMP(3),
    PRIMARY KEY (id) NOT ENFORCED
);
INSERT OVERWRITE laife_stream.dwd_trade_order_detail
SELECT od.id, od.order_id, oi.user_id, od.sku_id, oi.province_id, od.source_type, od.order_price, od.sku_num,
       (od.order_price * od.sku_num) AS split_original_amount, COALESCE(od.split_activity_amount, 0.0) AS split_activity_amount,
       COALESCE(od.split_coupon_amount, 0.0) AS split_coupon_amount, od.split_total_amount, oi.order_status, od.create_time
FROM laife_stream.ods_order_detail od
JOIN laife_stream.ods_order_info oi ON od.order_id = oi.id;

-- =========================================
-- 模块三：核心用户维度表 (dim_user_info)
-- =========================================
CREATE TABLE IF NOT EXISTS laife_stream.dim_user_info (
    id BIGINT, login_name STRING, nick_name STRING, name STRING, phone_num STRING,
    email STRING, user_level STRING, birthday DATE, gender STRING, create_time TIMESTAMP(3),
    operate_time TIMESTAMP(3),
    PRIMARY KEY (id) NOT ENFORCED
);
INSERT OVERWRITE laife_stream.dim_user_info
SELECT id, login_name, nick_name, name, phone_num, email, user_level, birthday, gender, create_time, operate_time
FROM laife_stream.ods_user_info;

-- =========================================
-- 模块四：优惠券及活动维表 (dim_coupon_info, dim_activity_rule)
-- =========================================
CREATE TABLE IF NOT EXISTS laife_stream.dim_coupon_info (
    id BIGINT, coupon_name STRING, coupon_type STRING, condition_amount DECIMAL(16, 2),
    condition_num BIGINT, activity_id BIGINT, benefit_amount DECIMAL(16, 2),
    benefit_discount DECIMAL(16, 2), create_time TIMESTAMP(3), range_type STRING,
    PRIMARY KEY (id) NOT ENFORCED
);
INSERT OVERWRITE laife_stream.dim_coupon_info
SELECT id, coupon_name, coupon_type, condition_amount, condition_num, activity_id, benefit_amount, benefit_discount, create_time, range_type
FROM laife_stream.ods_coupon_info;

CREATE TABLE IF NOT EXISTS laife_stream.dim_activity_rule (
    activity_rule_id BIGINT, activity_id BIGINT, activity_type STRING, condition_amount DECIMAL(16, 2),
    condition_num BIGINT, benefit_amount DECIMAL(16, 2), benefit_discount DECIMAL(16, 2),
    benefit_level BIGINT, activity_name STRING, start_time TIMESTAMP(3), end_time TIMESTAMP(3),
    create_time TIMESTAMP(3), PRIMARY KEY (activity_rule_id) NOT ENFORCED
);
INSERT OVERWRITE laife_stream.dim_activity_rule
SELECT ar.id, ar.activity_id, ar.activity_type, ar.condition_amount, ar.condition_num, ar.benefit_amount, ar.benefit_discount, ar.benefit_level,
ai.activity_name, ai.start_time, ai.end_time, ai.create_time
FROM laife_stream.ods_activity_rule ar
LEFT JOIN laife_stream.ods_activity_info ai ON ar.activity_id = ai.id;

-- =========================================
-- 模块五：支付、退款、履约明细事实表
-- =========================================
CREATE TABLE IF NOT EXISTS laife_stream.dwd_trade_pay_detail (
    id BIGINT, order_id BIGINT, user_id BIGINT, alipay_trade_no STRING, total_amount DECIMAL(16, 2),
    subject STRING, payment_type STRING, payment_time TIMESTAMP(3), PRIMARY KEY (id) NOT ENFORCED
);
INSERT OVERWRITE laife_stream.dwd_trade_pay_detail
SELECT id, order_id, user_id, alipay_trade_no, total_amount, subject, payment_type, payment_time 
FROM laife_stream.ods_payment_info WHERE payment_status = '1602';

CREATE TABLE IF NOT EXISTS laife_stream.dwd_trade_refund_detail (
    id BIGINT, user_id BIGINT, order_id BIGINT, sku_id BIGINT, refund_type STRING, refund_num BIGINT,
    refund_amount DECIMAL(16, 2), refund_reason_type STRING, refund_status STRING, create_time TIMESTAMP(3),
    PRIMARY KEY (id) NOT ENFORCED
);
INSERT OVERWRITE laife_stream.dwd_trade_refund_detail
SELECT id, user_id, order_id, sku_id, refund_type, refund_num, refund_amount, refund_reason_type, refund_status, create_time
FROM laife_stream.ods_order_refund_info;

CREATE TABLE IF NOT EXISTS laife_stream.dwd_ware_order_task_detail (
    id BIGINT, sku_id BIGINT, sku_num BIGINT, task_id BIGINT, order_id BIGINT, ware_id BIGINT,
    task_status STRING, create_time TIMESTAMP(3), PRIMARY KEY (id) NOT ENFORCED
);
INSERT OVERWRITE laife_stream.dwd_ware_order_task_detail
SELECT d.id, d.sku_id, d.sku_num, d.task_id, t.order_id, t.ware_id, t.task_status, t.create_time
FROM laife_stream.ods_ware_order_task_detail d
JOIN laife_stream.ods_ware_order_task t ON d.task_id = t.id;

-- =========================================
-- 模块六：评价与核销互动事实表
-- =========================================
CREATE TABLE IF NOT EXISTS laife_stream.dwd_interaction_comment_info (
    id BIGINT, user_id BIGINT, nick_name STRING, sku_id BIGINT, spu_id BIGINT, order_id BIGINT,
    appraise STRING, comment_txt STRING, create_time TIMESTAMP(3), PRIMARY KEY (id) NOT ENFORCED
);
INSERT OVERWRITE laife_stream.dwd_interaction_comment_info
SELECT id, user_id, nick_name, sku_id, spu_id, order_id, appraise, comment_txt, create_time 
FROM laife_stream.ods_comment_info;

CREATE TABLE IF NOT EXISTS laife_stream.dwd_tool_coupon_used_detail (
    id BIGINT, coupon_id BIGINT, user_id BIGINT, order_id BIGINT, used_time TIMESTAMP(3), coupon_name STRING,
    PRIMARY KEY (id) NOT ENFORCED
);
INSERT OVERWRITE laife_stream.dwd_tool_coupon_used_detail
SELECT u.id, u.coupon_id, u.user_id, u.order_id, u.used_time, c.coupon_name
FROM laife_stream.ods_coupon_use u
LEFT JOIN laife_stream.ods_coupon_info c ON u.coupon_id = c.id
WHERE u.coupon_status = '1402';
"""

with DAG(
    'daily_all_dwd_dim_paimon_build_dag',
    default_args=default_args,
    schedule_interval='0 3 * * *', # 每天凌晨 3 点跑十库联洗
    catchup=False,
    tags=['dwd', 'dim', 'flink']
) as dag:

    run_dwd_dim_build_job = SSHOperator(
        task_id='build_all_dwd_dim_tables',
        ssh_conn_id='k8s_master_ssh',
        command=f"""
        kubectl exec -i -n lakehouse deployment/flink-jobmanager -- bash -c 'cat > /tmp/airflow_all_dwd_dim_build.sql && /opt/flink/bin/sql-client.sh -f /tmp/airflow_all_dwd_dim_build.sql' << 'EOF_SQL'
{FLINK_SQL_CONTENT}
EOF_SQL
        """
    )
