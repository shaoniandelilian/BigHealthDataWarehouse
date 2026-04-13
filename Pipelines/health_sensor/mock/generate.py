"""
generate.py — 模拟智能手环数据生成器
生成三个 Kafka topic 的数据：
  kafka_user_profile   — 用户信息/问卷（一次性）
  kafka_sensor_realtime — 实时秒级数据（持续）
  kafka_sensor_history  — 历史10分钟包（持续）
"""

import random
import time
from typing import Any


# ---------------------------------------------------------------------------
# 设备列表（模拟多用户）
# ---------------------------------------------------------------------------

ALL_DEVICE_IDS = [f"device_{i:04d}" for i in range(1, 601)]
DEVICE_IDS = ALL_DEVICE_IDS  # 兼容旧引用

def get_active_devices() -> list[str]:
    """每次调用返回随机子集，数量在 [200, 600] 之间"""
    k = random.randint(200, 600)
    return random.sample(ALL_DEVICE_IDS, k)


# ---------------------------------------------------------------------------
# Topic 1: kafka_user_profile
# ---------------------------------------------------------------------------

def gen_user_profile(device_id: str) -> dict[str, Any]:
    height = round(random.uniform(155, 185), 1)
    weight = round(random.uniform(45, 95), 1)
    return {
        "device_id": device_id,
        "user_id":   f"user_{device_id}",
        "sex":       random.randint(0, 1),
        "age":       random.randint(18, 65),
        "height":    height,
        "weight":    weight,
        "ISI":       random.randint(0, 28),
        "PHQ9":      random.randint(0, 27),
        "GAD7":      random.randint(0, 21),
        "MEQ":       random.randint(16, 86),
    }


# ---------------------------------------------------------------------------
# Topic 2: kafka_sensor_realtime（1秒/包，秒级高优先级数据）
# ---------------------------------------------------------------------------

# 每个设备维护一个简单状态，让数据有连续性
_device_state: dict[str, dict] = {}

def _get_state(device_id: str) -> dict:
    if device_id not in _device_state:
        _device_state[device_id] = {
            "hr":     random.randint(60, 80),
            "steps":  0,
            "posture": "sit",
        }
    return _device_state[device_id]


def gen_realtime(device_id: str, event_ts: int) -> dict[str, Any]:
    s = _get_state(device_id)
    # 心率随机游走
    s["hr"] = max(45, min(180, s["hr"] + random.randint(-3, 3)))
    # 步数累加（静止时不增）
    activity = random.choices([0, 1, 2, 3], weights=[50, 30, 15, 5])[0]
    if activity > 0:
        s["steps"] += random.randint(0, 2)
    # 姿态偶尔切换
    if random.random() < 0.02:
        s["posture"] = random.choice(["sit", "stand", "lie"])

    wearing = 0 if random.random() < 0.02 else 1  # 2% 概率未佩戴

    return {
        "device_id":      device_id,
        "event_ts":       event_ts,
        "heart_rate":     s["hr"] if wearing else None,
        "avg_heart_rate": max(45, min(180, s["hr"] + random.randint(-5, 5))) if wearing else None,
        "steps":          s["steps"],
        "wearing":        wearing,
        "activity_level": activity if wearing else 0,
        "posture":        s["posture"] if wearing else None,
    }


# ---------------------------------------------------------------------------
# Topic 3: kafka_sensor_history（10分钟/包，原始信号+分钟级指标）
# ---------------------------------------------------------------------------

def _gen_raw_signal(length: int, base: float, noise: float) -> list[float]:
    """生成带噪声的原始信号数组"""
    val = base
    out = []
    for _ in range(length):
        val += random.gauss(0, noise)
        out.append(round(val, 4))
    return out


def gen_history(device_id: str, ts_start: int, ts_end: int) -> dict[str, Any]:
    s = _get_state(device_id)
    hr = s["hr"]
    wearing_ratio = round(random.uniform(0.7, 1.0), 2)

    # PPG: 25Hz * 60s = 1500 samples/min，10分钟包取1分钟代表
    ppg_samples = 25 * 60
    # IMU: 10Hz * 60s = 600 samples/min
    imu_samples = 10 * 60
    # BIA: 0.1Hz * 60s = 6 samples/min
    bia_samples = 6

    return {
        "device_id":           device_id,
        "ts_start":            ts_start,
        "ts_end":              ts_end,
        # 分钟级指标
        "heart_rate_min":      round(hr + random.gauss(0, 2), 1),
        "rmssd":               round(random.uniform(20, 80), 2),
        "sdnn":                round(random.uniform(30, 100), 2),
        "pnn50":               round(random.uniform(0.05, 0.4), 3),
        "lf_hf_ratio":         round(random.uniform(0.5, 3.0), 3),
        "spo2":                round(random.uniform(95, 100), 1),
        "resp_rate":           round(random.uniform(12, 20), 1),
        "skin_temp":           round(random.uniform(33.0, 37.5), 2),
        "steps_min":           random.randint(0, 120),
        "activity_level_min":  round(random.uniform(0, 3), 2),
        "posture_min":         random.choice(["sit", "stand", "lie"]),
        "wearing_ratio":       wearing_ratio,
        # 原始信号
        "ppg_raw":     _gen_raw_signal(ppg_samples, 512, 10),
        "acc_x_raw":   _gen_raw_signal(imu_samples, 0.0, 0.5),
        "acc_y_raw":   _gen_raw_signal(imu_samples, 0.0, 0.5),
        "acc_z_raw":   _gen_raw_signal(imu_samples, 9.8, 0.3),
        "gyr_x_raw":   _gen_raw_signal(imu_samples, 0.0, 0.1),
        "gyr_y_raw":   _gen_raw_signal(imu_samples, 0.0, 0.1),
        "gyr_z_raw":   _gen_raw_signal(imu_samples, 0.0, 0.1),
        "bia_raw":     _gen_raw_signal(bia_samples, 500, 5),
    }
