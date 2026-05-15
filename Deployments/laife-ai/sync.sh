#!/bin/bash
# 在目标服务器 172.20.8.28 上运行
# 用法: ssh -A yingtiankai@172.20.8.28 bash /tmp/sync.sh
# -A 必须，把本地 SSH key 转发给目标用于连接源服务器
set -e

SRC="zhenrong@47.98.227.81"

rsync -avzP $SRC:/data/models/             /data/models/
rsync -avzP $SRC:/data/volumes/            /data/volumes/
rsync -avzP $SRC:/data/files/              /tmp/services-test/files/
rsync -avzP $SRC:/data/laife-ai/ques2label/ /tmp/services-test/laife-ai/ques2label/
rsync -avzP $SRC:/data/laife-ai/OCR/       /tmp/services-test/laife-ai/OCR/
rsync -avzP $SRC:/data/laife-ai/docs/      /tmp/services-test/laife-ai/docs/
rsync -avzP $SRC:/data/realtime_rag_pipeline/data/        /tmp/services-test/realtime_rag_pipeline/data/
rsync -avzP $SRC:/data/realtime_rag_pipeline/data_process/ /tmp/services-test/realtime_rag_pipeline/data_process/
rsync -avzP $SRC:/data/realtime_rag_pipeline/logs/        /tmp/services-test/realtime_rag_pipeline/logs/

echo "Done. $(du -sh /data/models/ /data/volumes/ /tmp/services-test/files/ 2>/dev/null)"
