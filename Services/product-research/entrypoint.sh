#!/usr/bin/env bash
set -euo pipefail

# Start Flask in background
python3 app.py &

# Wait for Flask to be ready
sleep 2

# Cron loop: run cron_worker.sh every 30s
while true; do
    ./cron_worker.sh >> /app/logs/cron_worker.log 2>&1 || true
    sleep 30
done
