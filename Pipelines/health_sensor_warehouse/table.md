**全流式架构（All-Streaming）— 4 个 Kafka Topic → ODS → DWD/DIM → DWS**

**Kafka Source（4 个临时源表，不持久化）**
1. `kafka_user_profile` — 用户个人信息 / 问卷（维度数据）
2. `kafka_sleep_diary` — 睡眠日报（每日一条汇总）
3. `kafka_sensor_hrv` — 心率 HRV 5分钟聚合快照
4. `kafka_sensor_event` — 传感器日志（统一 Topic，含 hrm/acc/ppg/grv/gyr/ped/lit）

**ODS 层（原始数据层 — 10 张 Paimon 表）**
1. **bhdw.ods_user_profile** — 用户个人信息表（主键：device_id）
2. **bhdw.ods_sleep_diary** — 睡眠日记表（主键：user_id, record_date）
3. **bhdw.ods_sensor_hrv** — 传感器 HRV 5分钟聚合表（主键：device_id, ts_start）
4. **bhdw.ods_sensor_acc** — 加速度计原始事件（主键：device_id, event_ts）
5. **bhdw.ods_sensor_grv** — 重力传感器原始事件（主键：device_id, event_ts）
6. **bhdw.ods_sensor_gyr** — 陀螺仪原始事件（主键：device_id, event_ts）
7. **bhdw.ods_sensor_hrm** — 心率原始事件（主键：device_id, event_ts）
8. **bhdw.ods_sensor_lit** — 光照传感器原始事件（主键：device_id, event_ts）
9. **bhdw.ods_sensor_ped** — 计步器原始事件（主键：device_id, event_ts）
10. **bhdw.ods_sensor_ppg** — PPG 原始事件（主键：device_id, event_ts）

**DWD / DIM 层（明细 / 维度层 — 3 张 Paimon 表）**
11. **bhdw.dim_user_profile** — 用户维度表，含 BMI、失眠/抑郁/焦虑等级、时型分类（主键：device_id）
12. **bhdw.dwd_sleep_diary** — 睡眠明细表，含睡眠质量和晚睡标记（主键：user_id, record_date）
13. **bhdw.dwd_sensor_hrv** — HRV 明细表，含活动强度和 HRV 质量标签（主键：device_id, ts_start）

**DWS 层（汇总数据层 — 1 张 Paimon 表）**
14. **bhdw.dws_user_report_1h** — 用户每小时综合报告，HRV 按小时聚合 LEFT JOIN dim_user_profile LEFT JOIN dwd_sleep_diary（主键：device_id, ds, hh）

总计 **14 张 Paimon 持久化表**，全部通过流处理（stream_job.sql）构建。

```mermaid
graph LR
    %% 定义节点样式
    classDef kafka fill:#fce4ec,stroke:#c2185b,stroke-width:1px,color:#000
    classDef ods fill:#e3f2fd,stroke:#1565c0,stroke-width:1px,color:#000
    classDef dwd fill:#e8f5e9,stroke:#2e7d32,stroke-width:1px,color:#000
    classDef dws fill:#fff3e0,stroke:#ef6c00,stroke-width:1px,color:#000

    %% ================= Kafka Source =================
    subgraph Kafka ["Kafka Source (4 topics)"]
        direction TB
        K1[kafka_user_profile]:::kafka
        K2[kafka_sleep_diary]:::kafka
        K3[kafka_sensor_hrv]:::kafka
        K4[kafka_sensor_event]:::kafka
    end

    %% ================= ODS 层 =================
    subgraph ODS ["ODS Layer (原始数据层)"]
        direction TB
        O1[(ods_user_profile)]:::ods
        O2[(ods_sleep_diary)]:::ods
        O3[(ods_sensor_hrv)]:::ods
        O4[(ods_sensor_acc)]:::ods
        O5[(ods_sensor_grv)]:::ods
        O6[(ods_sensor_gyr)]:::ods
        O7[(ods_sensor_hrm)]:::ods
        O8[(ods_sensor_lit)]:::ods
        O9[(ods_sensor_ped)]:::ods
        O10[(ods_sensor_ppg)]:::ods
    end

    %% ================= DWD / DIM 层 =================
    subgraph DWD ["DWD / DIM Layer (明细 / 维度层)"]
        direction TB
        D1[(dim_user_profile)]:::dwd
        D2[(dwd_sleep_diary)]:::dwd
        D3[(dwd_sensor_hrv)]:::dwd
    end

    %% ================= DWS 层 =================
    subgraph DWS ["DWS Layer (汇总数据层)"]
        direction TB
        W1[(dws_user_report_1h)]:::dws
    end

    %% ================= 依赖关系连线 =================

    %% Kafka → ODS
    K1 -- 流式写入 --> O1
    K2 -- 流式写入 --> O2
    K3 -- 流式写入 --> O3
    K4 -- "filter: acc" --> O4
    K4 -- "filter: grv" --> O5
    K4 -- "filter: gyr" --> O6
    K4 -- "filter: hrm" --> O7
    K4 -- "filter: lit" --> O8
    K4 -- "filter: ped" --> O9
    K4 -- "filter: ppg" --> O10

    %% ODS → DWD/DIM
    O1 -- 维度转换 --> D1
    O2 -- 解析标记 --> D2
    O3 -- 解析标签 --> D3

    %% DWD/DIM → DWS
    D1 -- LEFT JOIN --> W1
    D2 -- LEFT JOIN --> W1
    D3 -- LEFT JOIN --> W1
```
