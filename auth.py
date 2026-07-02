"""管理员登录、session cookie、API Key 的签发与校验。

安全要点：
- 密码用 PBKDF2-HMAC-SHA256（20 万次迭代）+ 随机 salt 存储，不存明文。
- API Key 只存 SHA256 摘要，明文仅创建时返回一次。
- session cookie 用 HMAC-SHA256 签名 (user, exp)，校验用 compare_digest 防时序攻击。
所有随机源走 secrets（密码学安全）。时间戳一律交给 SQLite 的 datetime('now')，
保证与 usage.cleanup 的日期比较格式完全一致（见 db 模块注释）。
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from pathlib import Path

import db

ADMIN_USERNAME = "admin"
_PASSWORD_ITERATIONS = 200_000
SESSION_TTL_SECONDS = 7 * 86400  # session 默认有效期 7 天
KEY_PREFIX = "tts-"


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), _PASSWORD_ITERATIONS
    ).hex()


def _sign(username: str, exp: int, secret: str) -> str:
    msg = f"{username}:{exp}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


# ---------- 管理员 ----------

def init_admin(credentials_file: Path) -> dict | None:
    """首次启动初始化：admin 表为空时生成随机密码与默认 API Key。

    返回凭证 dict（调用方打印到 stdout / 落盘 first-run-credentials.txt）；
    admin 已存在则返回 None，表示非首次启动。
    """
    if db.query("SELECT username FROM admin WHERE username = ?", (ADMIN_USERNAME,), one=True):
        return None
    password = secrets.token_urlsafe(12)
    salt = secrets.token_urlsafe(16)
    db.execute(
        "INSERT INTO admin(username, password_hash, salt) VALUES(?, ?, ?)",
        (ADMIN_USERNAME, _hash_password(password, salt), salt),
    )
    plain_key, _ = create_api_key("默认")
    creds = {"username": ADMIN_USERNAME, "password": password, "default_key": plain_key}
    credentials_file.write_text(
        "首次启动凭证（请妥善保管，确认记录后可删除本文件）\n"
        f"管理用户名: {ADMIN_USERNAME}\n"
        f"管理密码: {password}\n"
        f"默认 API Key: {plain_key}\n",
        encoding="utf-8",
    )
    return creds


def verify_admin(username: str, password: str) -> bool:
    row = db.query("SELECT password_hash, salt FROM admin WHERE username = ?", (username,), one=True)
    if not row:
        return False
    return hmac.compare_digest(row["password_hash"], _hash_password(password, row["salt"]))


# ---------- session cookie ----------

def get_or_create_session_secret(secret_file: Path) -> str:
    """加载或生成 session 签名密钥，持久化到 data/ 以便重启后旧 cookie 仍有效。"""
    if secret_file.exists():
        return secret_file.read_text(encoding="utf-8").strip()
    secret = secrets.token_urlsafe(48)
    secret_file.write_text(secret, encoding="utf-8")
    return secret


def make_session_cookie(username: str, secret: str) -> str:
    # 用单个名为 session 的 cookie 携带 user:exp:sig。若把 exp/sig 写成 Set-Cookie
    # 的属性，浏览器会把它们当非标准属性丢弃，回传时只剩 user，签名校验必失败。
    exp = int(time.time()) + SESSION_TTL_SECONDS
    sig = _sign(username, exp, secret)
    # HttpOnly 防 JS 读取，SameSite=Strict 防 CSRF；本地服务不强制 Secure（可能走 http 内网）。
    return f"session={username}:{exp}:{sig}; Path=/; HttpOnly; SameSite=Strict"


def parse_session_cookie(cookie_header: str | None, secret: str) -> str | None:
    """校验 Cookie 头里的 session cookie，成功返回 username，否则 None。"""
    if not cookie_header:
        return None
    for part in cookie_header.split(";"):
        part = part.strip()
        if not part.startswith("session="):
            continue
        value = part[len("session="):]
        try:
            user, exp, sig = value.split(":", 2)
        except ValueError:
            return None
        try:
            exp_int = int(exp)
        except ValueError:
            return None
        if exp_int < time.time():
            return None
        return user if hmac.compare_digest(sig, _sign(user, exp_int, secret)) else None
    return None


# ---------- API Key ----------

def create_api_key(name: str) -> tuple[str, int]:
    """新建 API Key，返回 (明文, id)。明文仅此一次返回给调用方，之后只存摘要。"""
    plain = KEY_PREFIX + secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(plain.encode("utf-8")).hexdigest()
    result = db.execute(
        "INSERT INTO api_keys(name, key_hash, created_at, enabled) VALUES(?, ?, datetime('now'), 1)",
        (name, key_hash),
    )
    return plain, result.lastrowid


def verify_api_key(plain: str) -> int | None:
    """校验 API Key，返回 key_id 或 None；命中则更新 last_used_at。"""
    if not plain:
        return None
    key_hash = hashlib.sha256(plain.encode("utf-8")).hexdigest()
    row = db.query("SELECT id, enabled FROM api_keys WHERE key_hash = ?", (key_hash,), one=True)
    if not row or row["enabled"] != 1:
        return None
    db.execute("UPDATE api_keys SET last_used_at = datetime('now') WHERE id = ?", (row["id"],))
    return row["id"]


def list_api_keys() -> list[dict]:
    rows = db.query(
        "SELECT id, name, created_at, last_used_at, enabled FROM api_keys ORDER BY id DESC"
    )
    return [dict(r) for r in rows]


def set_key_enabled(key_id: int, enabled: bool) -> None:
    db.execute("UPDATE api_keys SET enabled = ? WHERE id = ?", (1 if enabled else 0, key_id))


def rename_key(key_id: int, name: str) -> None:
    db.execute("UPDATE api_keys SET name = ? WHERE id = ?", (name, key_id))


def delete_key(key_id: int) -> None:
    db.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
