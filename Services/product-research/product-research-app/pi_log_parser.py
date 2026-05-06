#!/usr/bin/env python3
"""实时解析 pi --mode json 的 NDJSON 流，输出可读的 agent 内部过程日志。
用法: pi --mode json ... | python3 pi_log_parser.py
  或: tail -f raw.jsonl | python3 pi_log_parser.py
"""
import sys, json
from datetime import datetime

def ts():
    return datetime.now().strftime("%H:%M:%S")

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        e = json.loads(line)
    except json.JSONDecodeError:
        continue

    t = e.get("type", "")

    if t == "tool_execution_start":
        name = e.get("toolName", "")
        args = e.get("args", {})
        if name == "bash":
            print(f"[{ts()}] [TOOL] bash: {args.get('command','')[:200]}", flush=True)
        elif name == "write":
            print(f"[{ts()}] [TOOL] write: {args.get('path','')}", flush=True)
        elif name == "read":
            print(f"[{ts()}] [TOOL] read: {args.get('path','')}", flush=True)
        elif name == "edit":
            print(f"[{ts()}] [TOOL] edit: {args.get('path','')}", flush=True)
        else:
            print(f"[{ts()}] [TOOL] {name}: {json.dumps(args, ensure_ascii=False)[:200]}", flush=True)

    elif t == "tool_execution_end":
        name = e.get("toolName", "")
        err = e.get("isError", False)
        result = e.get("result", {})
        text = ""
        for c in result.get("content", []):
            if c.get("type") == "text":
                text += c.get("text", "")
        status = "FAIL" if err else "OK"
        preview = text.strip().replace("\n", " ")[:150]
        print(f"[{ts()}]   [{status}] {preview}", flush=True)

    elif t == "message_update":
        ae = e.get("assistantMessageEvent", {})
        aet = ae.get("type", "")
        if aet == "text_end":
            text = ae.get("content", "")
            print(f"[{ts()}] [TEXT] {text[:300]}", flush=True)
        elif aet == "thinking_end":
            text = ae.get("content", "")
            print(f"[{ts()}] [THINK] {text[:200]}", flush=True)

    elif t == "turn_end":
        msg = e.get("message", {})
        usage = msg.get("usage", {})
        inp = usage.get("input", 0)
        out = usage.get("output", 0)
        cache = usage.get("cacheRead", 0)
        print(f"[{ts()}] -- turn end (in:{inp} out:{out} cache:{cache}) --", flush=True)

    elif t == "agent_end":
        print(f"[{ts()}] [END] agent done", flush=True)
