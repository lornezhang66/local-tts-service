"""调用记录：写入、汇总、过期清理、磁盘占用统计。

usage_log 每次合成都写一条（成功 / 失败都记），是本服务唯一会持续增长的
持久化数据。清理策略见 cleanup()：按天删除，由 server.py 的后台线程定期触发，
也可在管理页手动触发。时间戳一律用 SQLite datetime('now')，确保与 cleanup
里的 datetime('now','-N days') 比较时格式一致。
"""
from __future__ import annotations

from pathlib import Path

import db

_ERROR_MAX_LEN = 200


def log_call(
    key_id: int | None,
    text_len: int,
    audio_duration: float | None,
    latency_ms: int | None,
    status: str,
    error: str | None = None,
) -> None:
    err = (error[:_ERROR_MAX_LEN] if error else None)
    db.execute(
        "INSERT INTO usage_log(key_id, ts, text_len, audio_duration, latency_ms, status, error) "
        "VALUES(?, datetime('now'), ?, ?, ?, ?, ?)",
        (key_id, text_len, audio_duration, latency_ms, status, err),
    )


def summary() -> list[dict]:
    """按 API Key 汇总：总次数、成功次数、合成总时长（秒）、最近使用时间。"""
    rows = db.query(
        """
        SELECT k.id, k.name,
               COUNT(*) AS total,
               SUM(CASE WHEN u.status = 'ok' THEN 1 ELSE 0 END) AS ok_count,
               COALESCE(SUM(u.audio_duration), 0) AS total_audio,
               MAX(u.ts) AS last_used
        FROM usage_log u LEFT JOIN api_keys k ON u.key_id = k.id
        GROUP BY k.id, k.name
        ORDER BY k.id DESC
        """
    )
    return [dict(r) for r in rows]


def recent(limit: int = 100) -> list[dict]:
    rows = db.query(
        "SELECT u.id, u.ts, u.text_len, u.audio_duration, u.latency_ms, u.status, u.error, k.name "
        "FROM usage_log u LEFT JOIN api_keys k ON u.key_id = k.id "
        "ORDER BY u.id DESC LIMIT ?",
        (limit,),
    )
    return [dict(r) for r in rows]


def count() -> int:
    row = db.query("SELECT COUNT(*) AS n FROM usage_log", one=True)
    return int(row["n"]) if row else 0


def cleanup(days: int) -> int:
    """删除 days 天前的调用记录，返回删除条数。"""
    # datetime('now') 与写入时的 datetime('now') 同源同格式，字符串比较安全。
    result = db.execute(
        "DELETE FROM usage_log WHERE ts < datetime('now', ?)",
        (f"-{int(days)} days",),
    )
    return result.rowcount


def data_size(data_dir: Path) -> int:
    """递归统计 data/ 目录占用字节数，供管理页展示磁盘状态。"""
    total = 0
    for path in data_dir.rglob("*"):
        if path.is_file():
            total += path.stat().st_size
    return total
