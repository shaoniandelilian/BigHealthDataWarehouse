-- =========================================================================
-- 这是专门用于放入 StreamPark 的【纯实时 DWD 宽表滚水线】!!!
-- 它不是定时的，而是跑起来 7x24 小时永远不停止的流处理。
-- =========================================================================

-- 1. 指定执行模式为：流式（Streaming）！
SET 'execution.runtime-mode' = 'streaming';

-- Paimon 环境变量配置 (请在 StreamPark 或者 Flink CLI 里填入真实的 AK/SK)
CREATE CATALOG IF NOT EXISTS paimon_catalog WITH (
  'type' = 'paimon',
  'warehouse' = 's3://fluss/paimon',
  's3.endpoint' = 'https://oss-cn-hangzhou-internal.aliyuncs.com',
  's3.access-key' = '${PAIMON_S3_ACCESS_KEY}', -- 请在 StreamPark 环境变量或 K8s 挂载配置中指定真实秘钥
  's3.secret-key' = '${PAIMON_S3_SECRET_KEY}'
);
USE CATALOG paimon_catalog;

-- (此处省略了建表语句，假设你在跑这个任务前，DWD 表已经存在了)

-- 2. 注意这里的关键字变成了 【INSERT INTO】 ！！！
-- 因为 Paimon 是一张具有 Primary Key 的表，Flink 在流数据里如果遇到订单状态变更，
-- 它会发出 Update 消息，Paimon 接收到同样的 ID 后会自动覆盖旧数据，达到实时滚动的效果。
INSERT INTO paimon_catalog.laife_stream.dwd_trade_order_detail
SELECT 
    od.id,
    od.order_id,
    oi.user_id,
    od.sku_id,
    oi.province_id,
    od.source_type,
    od.order_price,
    od.sku_num,
    (od.order_price * od.sku_num) AS split_original_amount,
    COALESCE(act.split_activity_amount, 0.0) AS split_activity_amount,
    COALESCE(cou.split_coupon_amount, 0.0) AS split_coupon_amount,
    od.split_total_amount,
    oi.order_status,
    od.create_time
FROM paimon_catalog.laife_stream.ods_order_detail od
-- 注意：在流处理中，这里的 JOIN 叫做 “双流 JOIN / 状态 JOIN”
-- Flink 会把 ods_order_detail 和 ods_order_info 的数据暂存在内存状态里互相等待匹配
JOIN paimon_catalog.laife_stream.ods_order_info oi ON od.order_id = oi.id
LEFT JOIN paimon_catalog.laife_stream.ods_order_detail_activity act ON od.id = act.order_detail_id
LEFT JOIN paimon_catalog.laife_stream.ods_order_detail_coupon cou ON od.id = cou.order_detail_id;
