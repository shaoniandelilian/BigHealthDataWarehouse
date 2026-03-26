-- ============================================================
-- 00_catalog.sql — Paimon Catalog & Database Initialization
-- ============================================================

-- Flink runtime settings (BATCH mode for bulk load)
SET 'execution.runtime-mode' = 'batch';
SET 'sql-client.execution.result-mode' = 'tableau';
SET 'table.exec.sink.not-null-enforcer' = 'DROP';
SET 'table.exec.sink.upsert-materialize' = 'NONE';
SET 'parallelism.default' = '1';
SET 'execution.checkpointing.interval' = '1min';

-- Create Paimon catalog
CREATE CATALOG paimon_catalog WITH (
    'type' = 'paimon',
    'warehouse' = 's3://fluss/paimon',
    's3.endpoint' = '<your-endpoint>',
    's3.access-key' = '<your-access-key>',
    's3.secret-key' = '<your-secret-key>',
    's3.path.style.access' = 'false'
);

USE CATALOG paimon_catalog;

-- Create unified database for all warehouse layers
CREATE DATABASE IF NOT EXISTS bhdw;
