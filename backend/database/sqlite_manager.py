import sqlite3
import logging
from typing import Any, Dict, List, Optional
from backend.config import WAREHOUSE_DB_PATH

logger = logging.getLogger("dwh.database")

class SQLiteManager:
    def __init__(self, db_path=None):
        self.db_path = str(db_path or WAREHOUSE_DB_PATH)

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=20.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    def execute_script(self, sql_script: str):
        with self.get_connection() as conn:
            conn.executescript(sql_script)
            conn.commit()

    def execute_query(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def execute_non_query(self, query: str, params: tuple = ()) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            return cursor.lastrowid

    def execute_many(self, query: str, param_list: List[tuple]) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, param_list)
            conn.commit()
            return cursor.rowcount

    def table_exists(self, table_name: str) -> bool:
        res = self.execute_query(
            "SELECT count(*) as cnt FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
        return res[0]["cnt"] > 0

    def get_table_columns(self, table_name: str) -> List[Dict[str, Any]]:
        if not self.table_exists(table_name):
            return []
        rows = self.execute_query(f"PRAGMA table_info({table_name});")
        return [
            {
                "cid": r["cid"],
                "name": r["name"],
                "type": r["type"],
                "notnull": r["notnull"],
                "dflt_value": r["dflt_value"],
                "pk": r["pk"]
            }
            for r in rows
        ]

db_manager = SQLiteManager()
