# -*- coding: utf-8 -*-
import sqlite3
import json
import logging
from typing import List, Dict, Any, Optional

from core.context import Context

logger = logging.getLogger("ReviewStore")

class ReviewStore:
    """
    基于本地 SQLite 的超轻量级审核数据持久化层。
    没有额外依赖，保证待审核数据不会因为服务器重启而丢失。
    """
    def __init__(self, db_path: str = "logs/pending_reviews.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS pending_reviews (
                    id TEXT PRIMARY KEY,
                    context_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()

    def save_pending_context(self, context_id: str, context: Context):
        """保存被挂起的 Context"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            ctx_data = json.dumps(context.to_dict(), ensure_ascii=False)
            cursor.execute('''
                INSERT OR REPLACE INTO pending_reviews (id, context_json)
                VALUES (?, ?)
            ''', (context_id, ctx_data))
            conn.commit()
            logger.info(f"💾 Context {context_id} saved to pending queue.")

    def get_pending_records(self, limit: int = 50) -> List[Dict[str, Any]]:
        """API端获取待审核列表"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id, context_json, created_at FROM pending_reviews ORDER BY created_at ASC LIMIT ?', (limit,))
            rows = cursor.fetchall()
            
        results = []
        for row in rows:
            record_id = row[0]
            ctx_dict = json.loads(row[1])
            created_at = row[2]
            # 为了前端展示，只提取关键字段而不是整坨大向量
            results.append({
                "id": record_id,
                "created_at": created_at,
                "raw_data": ctx_dict.get("raw_data"),
                "metadata": ctx_dict.get("metadata")
            })
        return results

    def get_and_delete_context(self, context_id: str) -> Optional[Context]:
        """审核完毕后，取出 Context 并从挂起队伍中删除"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT context_json FROM pending_reviews WHERE id = ?', (context_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
                
            ctx_dict = json.loads(row[0])
            cursor.execute('DELETE FROM pending_reviews WHERE id = ?', (context_id,))
            conn.commit()
            
            return Context.from_dict(ctx_dict)
