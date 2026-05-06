#!/usr/bin/env bash
# cron_worker.sh — 扫描 tasks/ 下 pending 任务，派发给 pi agent 调研
# crontab: * * * * * /path/to/cron_worker.sh >> /path/to/cron_worker.log 2>&1
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
TASKS_DIR="$APP_DIR/tasks"
CONVOS_DIR="$APP_DIR/conversations"
BACKEND="http://127.0.0.1:5001"
SKILL_DIR="$HOME/.kiro/skills"
LOCKFILE="$APP_DIR/.cron_worker.lock"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# 防并发
exec 9>"$LOCKFILE"
flock -n 9 || { log "⏭ 已有 worker 运行，跳过"; exit 0; }

update_convo() { # $1=cid $2=status $3=extra_fields(optional python dict literal)
    python3 -c "
import json,os,sys
from datetime import datetime
p=os.path.join(sys.argv[1],sys.argv[2]+'.json')
if not os.path.exists(p): sys.exit()
d=json.load(open(p))
d['status']=sys.argv[3]
d['updated']=datetime.now().strftime('%Y-%m-%d %H:%M')
if sys.argv[3]=='done': d['completed_at']=d['updated']
if sys.argv[3]=='error': d['error']='调研失败，未采集到数据'
json.dump(d,open(p,'w'),ensure_ascii=False,indent=2)
" "$CONVOS_DIR" "$1" "$2"
}

found=0
for task_file in "$TASKS_DIR"/*.json; do
    [ -f "$task_file" ] || continue
    [[ "$(basename "$task_file")" == *_* ]] && continue

    read -r status cid topic < <(python3 -c "
import json,sys
d=json.load(open(sys.argv[1]))
print(d['status'],d['cid'],d['topic'])
" "$task_file") || continue

    [ "$status" != "pending" ] && continue
    found=1
    log "🚀 任务: $cid | $topic"

    # 标记 dispatched
    python3 -c "
import json,sys
from datetime import datetime
f=sys.argv[1]; d=json.load(open(f))
d['status']='dispatched'; d['dispatched_at']=datetime.now().astimezone().isoformat()
json.dump(d,open(f,'w'),ensure_ascii=False,indent=2)
" "$task_file"

    # 调用 pi（30 分钟超时），json 流写入原始日志，同时解析为可读日志
    mkdir -p "$APP_DIR/logs"
    PI_RAW="$APP_DIR/logs/pi-${cid}.raw.jsonl"
    PI_LOG="$APP_DIR/logs/pi-${cid}.log"
    timeout 1800 pi --mode json --no-session \
        --skill "$SKILL_DIR/product-research" \
        --skill "$SKILL_DIR/scrapling-official" \
        "你是产品调研助手。请对「${topic}」进行市场调研。
每采集到一条产品记录，立即用 bash 执行:
curl -s -X POST ${BACKEND}/api/subagent/record/${cid} -H 'Content-Type: application/json' -d '{\"record\":{...}}'
record 字段: product_name, brand, source_platform, product_url, dosage_form, pack_size, price, core_selling_points, core_ingredients, claim_direction, public_heat_signal, target_population（全部为字符串）。
目标 15-30 条。禁止访问京东/天猫/淘宝/拼多多。开始。" \
        2>/dev/null | tee "$PI_RAW" | python3 "$APP_DIR/pi_log_parser.py" > "$PI_LOG" 2>&1 || true

    # 判断结果
    count=$(curl -sf "${BACKEND}/api/conversation/${cid}/records?offset=0" \
        | python3 -c "import json,sys;print(json.load(sys.stdin).get('total',0))" 2>/dev/null || echo 0)

    if [ "$count" -gt 0 ]; then
        log "✅ 完成: $cid | ${count} 条"
        python3 -c "import json,sys;f=sys.argv[1];d=json.load(open(f));d['status']='completed';json.dump(d,open(f,'w'),ensure_ascii=False,indent=2)" "$task_file"
        update_convo "$cid" "done"
    else
        log "❌ 失败: $cid | 无记录"
        python3 -c "import json,sys;f=sys.argv[1];d=json.load(open(f));d['status']='failed';json.dump(d,open(f,'w'),ensure_ascii=False,indent=2)" "$task_file"
        update_convo "$cid" "error"
    fi
done

[ "$found" -eq 0 ] && log "💤 无 pending 任务"
