# -*- coding: utf-8 -*-
import sqlite3
import logging
import json
import os
import uuid
import time
from typing import List, Dict, Any, Optional

logger = logging.getLogger("StateManager")

class StateManager:
    """
    轻量级的 SQLite 流水线运行状态追踪持久化层。
    确保不同 Pipeline 配置（预设）有独立的表，并且算子支持热插拔自动更新 Schema。
    """
    def __init__(self, db_path: str = "logs/pipeline_states.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        # 确保数据库文件可创建，不需要建全局表，全都是基于 Pipeline Name 动态表
        with sqlite3.connect(self.db_path) as conn:
            conn.commit()

    def _get_table_name(self, pipeline_name: str) -> str:
        """根据 yaml 名字生成表名, 滤除特殊字符"""
        # configs/pipeline_doc_ai.yaml -> pipeline_doc_ai
        base_name = os.path.splitext(os.path.basename(pipeline_name))[0]
        sanitized = "".join([c if c.isalnum() else "_" for c in base_name])
        return f"state_{sanitized}"

    def sync_table(self, pipeline_name: str, processor_names: List[str]):
        """
        初始化或更新针对该预设的表结构（热插拔支持）。
        如果检测有新算子加入，则自动 ALTER TABLE 增加状态和耗时列。
        """
        table_name = self._get_table_name(pipeline_name)
        
        # 基础骨架构建
        create_sql = f'''
            CREATE TABLE IF NOT EXISTS {table_name} (
                run_id TEXT PRIMARY KEY,
                doc_id TEXT,
                source_file TEXT,
                global_status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                error_message TEXT
            )
        '''
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(create_sql)
            
            # 获取当前所有列
            cursor.execute(f"PRAGMA table_info({table_name})")
            existing_columns = [row[1] for row in cursor.fetchall()]
            
            # 动态插入新发现的 processor 辅助列
            for proc in processor_names:
                # 给每个算子建立状态列和耗时列
                status_col = f"{proc}_status"
                cost_col = f"{proc}_cost"
                
                if status_col not in existing_columns:
                    logger.info(f"🔧 Hot-plug detected! Adding new column [{status_col}] to table `{table_name}`")
                    cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {status_col} TEXT DEFAULT 'pending'")
                
                if cost_col not in existing_columns:
                    cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {cost_col} REAL DEFAULT 0.0")
            
            conn.commit()
            
    def init_run(self, pipeline_name: str, run_id: str, doc_id: str, source_file: str):
        """流水线新文档开始流转"""
        table_name = self._get_table_name(pipeline_name)
        with sqlite3.connect(self.db_path) as conn:
             cursor = conn.cursor()
             # 插入新的一条追踪记录
             query = f'''
                 INSERT OR REPLACE INTO {table_name} 
                 (run_id, doc_id, source_file, global_status)
                 VALUES (?, ?, ?, 'running')
             '''
             cursor.execute(query, (run_id, doc_id, source_file))
             conn.commit()
             
    def update_global_status(self, pipeline_name: str, run_id: str, status: str, errors: List[str] = None):
        """流转完结、出错、挂起时更新总状态"""
        table_name = self._get_table_name(pipeline_name)
        err_msg = json.dumps(errors, ensure_ascii=False) if errors else ""
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            query = f'''
                UPDATE {table_name} 
                SET global_status = ?, error_message = ?, updated_at = CURRENT_TIMESTAMP
                WHERE run_id = ?
            '''
            cursor.execute(query, (status, err_msg, run_id))
            conn.commit()
            
    def update_step_status(self, pipeline_name: str, run_id: str, processor_name: str, status: str, cost: float = 0.0):
        """当一个算子完成或失败时打点"""
        table_name = self._get_table_name(pipeline_name)
        status_col = f"{processor_name}_status"
        cost_col = f"{processor_name}_cost"
        
        with sqlite3.connect(self.db_path) as conn:
             cursor = conn.cursor()
             try:
                 query = f'''
                     UPDATE {table_name}
                     SET {status_col} = ?, {cost_col} = ?, updated_at = CURRENT_TIMESTAMP
                     WHERE run_id = ?
                 '''
                 cursor.execute(query, (status, cost, run_id))
             except sqlite3.OperationalError as e:
                 # 防止由于有非常特殊命名或未预期的情况导致的 SQL 崩毁，做兜底放行
                 logger.warning(f"Failed to tracking step status for {processor_name}: {e}")
             conn.commit()

# 提供全局单例模式供 pipeline 引擎轻量化调用
global_state_manager = StateManager()
