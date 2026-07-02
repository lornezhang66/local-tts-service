"""SQLite 连接、建表与并发控制。

所有持久化模块（auth / usage）通过本模块的 query / execute 访问数据库，
统一用一把进程级全局锁串行化写操作。本地 TTS 服务的并发量是个位数，
全局锁的简单性远胜过多连接 WAL 并发调优的复杂度——这是刻意的取舍。
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import NamedTuple

SCHEMA = """
CREATE TABLE IF NOT EXISTS admin (
  username TEXT PRIMARY KEY,
  password_hash TEXT NOT NULL,
  salt TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS api_keys (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  key_hash TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL,
  last_used_at TEXT,
  enabled INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS usage_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  key_id INTEGER,
  ts TEXT NOT NULL,
  text_len INTEGER NOT NULL,
  audio_duration REAL,
  latency_ms INTEGER,
  status TEXT NOT NULL,
  error TEXT
);
CREATE INDEX IF NOT EXISTS idx_usage_ts ON usage_log(ts);
"""

# 进程级写锁：sqlite3 默认连接不允许跨线程，且并发写会撞 SQLITE_BUSY。
# 用一把全局锁串行化所有访问，把并发问题彻底消灭，代价是吞吐——本地服务够用。
_lock = threading.Lock()
_db_path: Path | None = None


class ExecResult(NamedTuple):
    """execute 的返回：INSERT 取 lastrowid，UPDATE/DELETE 取 rowcount。"""
    lastrowid: int
    rowcount: int


def init_db(data_dir: Path) -> None:
    """创建数据目录、数据库文件并建表。进程启动调用一次。"""
    global _db_path
    data_dir.mkdir(parents=True, exist_ok=True)
    _db_path = data_dir / "tts.db"
    conn = _connect()
    try:
        # WAL 降低写阻塞、提升读并发；它是数据库文件的持久属性，设一次即可。
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def _connect() -> sqlite3.Connection:
    if _db_path is None:
        raise RuntimeError("db.init_db 未被调用")
    # check_same_thread=False 配合全局锁，允许任意线程在持锁时访问。
    conn = sqlite3.connect(_db_path, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def query(sql: str, params: tuple = (), one: bool = False):
    """只读查询。one=True 返回单行（sqlite3.Row）或 None，否则返回行列表。"""
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()
    if one:
        return rows[0] if rows else None
    return rows


def execute(sql: str, params: tuple = ()) -> ExecResult:
    """写操作（INSERT / UPDATE / DELETE），返回 ExecResult。"""
    with _lock:
        conn = _connect()
        try:
            cur = conn.execute(sql, params)
            result = ExecResult(cur.lastrowid or 0, cur.rowcount)
            conn.commit()
        finally:
            conn.close()
    return result
