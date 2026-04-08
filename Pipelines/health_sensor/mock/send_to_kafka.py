#!/usr/bin/env python3
"""
send_to_kafka.py — 模拟手环数据发送到 Kafka

三个 topic 并发运行：
  kafka_user_profile    — 启动时发送一次，之后每隔 --profile-interval 秒重发
  kafka_sensor_realtime — 每秒发送一条（每个设备）
  kafka_sensor_history  — 每10分钟发送一条（每个设备）
"""

import argparse
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from generate import DEVICE_IDS, gen_user_profile, gen_realtime, gen_history

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

STOP = Event()


def make_producer(bootstrap_servers: str):
    from kafka import KafkaProducer
    return KafkaProducer(
        bootstrap_servers=bootstrap_servers,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        acks=1,
        linger_ms=10,
        batch_size=32768,
    )


# ---------------------------------------------------------------------------
# 三个发送线程
# ---------------------------------------------------------------------------

def thread_user_profile(bootstrap_servers: str, topic: str, interval: int):
    producer = make_producer(bootstrap_servers)
    try:
        while not STOP.is_set():
            for device_id in DEVICE_IDS:
                producer.send(topic, value=gen_user_profile(device_id))
            producer.flush()
            log.info("[user_profile] Sent %d records", len(DEVICE_IDS))
            STOP.wait(interval)
    finally:
        producer.close()


def thread_realtime(bootstrap_servers: str, topic: str, speed_factor: float):
    """每 1/speed_factor 秒发一轮（所有设备）"""
    producer = make_producer(bootstrap_servers)
    interval = 1.0 / speed_factor
    sent = 0
    try:
        while not STOP.is_set():
            ts = int(time.time() * 1000)
            for device_id in DEVICE_IDS:
                producer.send(topic, value=gen_realtime(device_id, ts))
            sent += len(DEVICE_IDS)
            if sent % (100 * len(DEVICE_IDS)) == 0:
                log.info("[realtime] Sent %d records total", sent)
            STOP.wait(interval)
    finally:
        producer.flush()
        producer.close()


def thread_history(bootstrap_servers: str, topic: str, speed_factor: float):
    """每 600/speed_factor 秒发一轮（所有设备）"""
    producer = make_producer(bootstrap_servers)
    interval = 600.0 / speed_factor
    sent = 0
    try:
        while not STOP.is_set():
            ts_start = int(time.time() * 1000)
            ts_end   = ts_start + 600_000
            for device_id in DEVICE_IDS:
                producer.send(topic, value=gen_history(device_id, ts_start, ts_end))
            sent += len(DEVICE_IDS)
            log.info("[history] Sent %d records total", sent)
            STOP.wait(interval)
    finally:
        producer.flush()
        producer.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="模拟手环数据发送到 Kafka")
    parser.add_argument("--bootstrap-servers",  default="localhost:30092")
    parser.add_argument("--topic-user-profile", default="kafka_user_profile")
    parser.add_argument("--topic-realtime",     default="kafka_sensor_realtime")
    parser.add_argument("--topic-history",      default="kafka_sensor_history")
    parser.add_argument("--speed-factor",       type=float, default=1.0,
                        help="加速倍数：2.0 表示2倍速，realtime变0.5s/包，history变5min/包")
    parser.add_argument("--profile-interval",   type=int, default=120,
                        help="用户信息重发间隔（秒），默认1小时")
    args = parser.parse_args()

    log.info("Bootstrap: %s | devices: %d | speed: %.1fx",
             args.bootstrap_servers, len(DEVICE_IDS), args.speed_factor)

    tasks = [
        (thread_user_profile, args.bootstrap_servers, args.topic_user_profile, args.profile_interval),
        (thread_realtime,     args.bootstrap_servers, args.topic_realtime,     args.speed_factor),
        (thread_history,      args.bootstrap_servers, args.topic_history,      args.speed_factor),
    ]

    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(fn, *fn_args) for fn, *fn_args in tasks]
            for f in futures:
                f.result()
    except KeyboardInterrupt:
        log.info("Stopping...")
        STOP.set()

    log.info("Done.")


if __name__ == "__main__":
    main()
