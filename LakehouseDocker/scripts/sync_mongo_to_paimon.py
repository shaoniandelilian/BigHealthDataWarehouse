#!/usr/bin/env python3
"""
MongoDB phdata 全量同步 → OSS → Paimon
宿主机 cron: 0 2 * * * /usr/bin/python3 /root/sync_mongo_to_paimon.py >> /var/log/sync_mongo.log 2>&1
"""

import json
import subprocess
import sys
import tempfile
from datetime import datetime

from bson import json_util
from pymongo import MongoClient

# ── 配置 ──
MONGO_URI = "mongodb://admin:strongpassword@47.98.227.81:8060"
MONGO_DB = "health_archives"
MONGO_COLLECTION = "phdata"

S3_ENDPOINT = "<your-endpoint>"
S3_ACCESS_KEY = "<your-access-key>"
S3_SECRET_KEY = "<your-secret-key>"
OSS_BUCKET = "fluss"
OSS_KEY = "paimon/_staging/health_agent/ods_phdata/phdata.json"

FLINK_NS = "lakehouse"
FLINK_DEPLOY = "deployment/flink-jobmanager"

FLINK_SQL = f"""
SET 'execution.runtime-mode' = 'batch';

CREATE CATALOG IF NOT EXISTS paimon_catalog WITH (
  'type' = 'paimon',
  'warehouse' = 's3://fluss/paimon',
  's3.endpoint' = '{S3_ENDPOINT}',
  's3.access-key' = '{S3_ACCESS_KEY}',
  's3.secret-key' = '{S3_SECRET_KEY}',
  's3.path.style.access' = 'false'
);
USE CATALOG paimon_catalog;

CREATE TEMPORARY TABLE oss_phdata_src (
  _id STRING,
  phdata_id STRING,
  report_id STRING,
  `project` STRING,
  `detail` STRING,
  `result` STRING,
  conclusion STRING,
  confidence STRING,
  `source` STRING,
  timestamp_data STRING,
  if_abnormal BOOLEAN,
  labels_json STRING,
  created_at STRING,
  updated_at STRING
) WITH (
  'connector' = 'filesystem',
  'path' = 's3://{OSS_BUCKET}/{OSS_KEY}',
  'format' = 'json'
);

CREATE TABLE IF NOT EXISTS laife.ods_phdata (
  _id STRING,
  phdata_id STRING,
  report_id STRING,
  `project` STRING,
  `detail` STRING,
  `result` STRING,
  conclusion STRING,
  confidence STRING,
  `source` STRING,
  timestamp_data STRING,
  if_abnormal BOOLEAN,
  labels_json STRING,
  created_at STRING,
  updated_at STRING,
  sync_time TIMESTAMP(3),
  PRIMARY KEY (_id) NOT ENFORCED
);

INSERT OVERWRITE laife.ods_phdata
SELECT
  _id, phdata_id, report_id, `project`, `detail`, `result`,
  conclusion, confidence, `source`, timestamp_data, if_abnormal,
  labels_json, CAST(created_at AS TIMESTAMP(3)), CAST(updated_at AS TIMESTAMP(3)), CURRENT_TIMESTAMP
FROM oss_phdata_src;
"""


def log(msg):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def step1_extract_and_upload():
    log("Step1: MongoDB → OSS ...")
    client = MongoClient(MONGO_URI)
    coll = client[MONGO_DB][MONGO_COLLECTION]

    def _to_str(v):
        """Unwrap BSON date objects and normalize to Flink SQL timestamp format."""
        if isinstance(v, dict) and "$date" in v:
            v = v["$date"]
        if v is None:
            return None
        # Convert ISO 8601 (2026-02-06T08:36:14.667Z) → SQL (2026-02-06 08:36:14.667)
        return str(v).replace("T", " ").rstrip("Z")

    lines = []
    for doc in coll.find():
        d = json.loads(json_util.dumps(doc))
        row = {
            "_id": str(doc["_id"]),
            "phdata_id": d.get("phdata_id"),
            "report_id": d.get("report_id"),
            "project": d.get("project"),
            "detail": d.get("detail"),
            "result": d.get("result"),
            "conclusion": d.get("conclusion"),
            "confidence": d.get("confidence"),
            "source": d.get("source"),
            "timestamp_data": _to_str(d.get("timestamp_data")),
            "if_abnormal": d.get("if_abnormal"),
            "labels_json": json.dumps(d.get("labels"), ensure_ascii=False) if d.get("labels") else None,
            "created_at": _to_str(d.get("created_at")),
            "updated_at": _to_str(d.get("updated_at")),
        }
        lines.append(json.dumps(row, ensure_ascii=False, default=str))
    client.close()
    log(f"  {len(lines)} docs fetched")

    import oss2
    auth = oss2.Auth(S3_ACCESS_KEY, S3_SECRET_KEY)
    bucket = oss2.Bucket(auth, S3_ENDPOINT, OSS_BUCKET)
    bucket.put_object(OSS_KEY, "\n".join(lines).encode("utf-8"))
    log(f"  uploaded to s3://{OSS_BUCKET}/{OSS_KEY}")


def step2_flink_load():
    log("Step2: Flink SQL → Paimon ...")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f:
        f.write(FLINK_SQL)
        sql_file = f.name

    cmd = [
        "kubectl", "exec", "-i", "-n", FLINK_NS, FLINK_DEPLOY, "--",
        "bash", "-c",
        "cat > /tmp/sync_phdata.sql && /opt/flink/bin/sql-client.sh -f /tmp/sync_phdata.sql",
    ]
    with open(sql_file) as stdin:
        r = subprocess.run(cmd, stdin=stdin, capture_output=True, text=True)

    if r.stdout:
        log(r.stdout)
    if r.returncode != 0:
        log(f"  FAILED: {r.stderr}")
        sys.exit(1)
    log("  done")


if __name__ == "__main__":
    log("===== sync_mongo start =====")
    step1_extract_and_upload()
    step2_flink_load()
    log("===== sync_mongo finish =====")
