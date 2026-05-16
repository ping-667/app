import sqlite3
import os
import csv
import hashlib
from pathlib import Path
from datetime import datetime


class Database:
    def __init__(self, db_path=None):
        if db_path is None:
            db_dir = Path(os.getenv('APPDATA')) / 'QQMonitor'
            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = db_dir / 'messages.db'
        self.db_path = str(db_path)
        self._init_schema()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    detected_at TEXT NOT NULL,
                    sender TEXT DEFAULT '未知',
                    content TEXT NOT NULL,
                    matched_keywords TEXT NOT NULL,
                    group_name TEXT DEFAULT '默认',
                    screenshot_path TEXT,
                    content_hash TEXT,
                    is_read INTEGER DEFAULT 0
                )
            """)

            # Migration: add user_id if upgrading from old schema
            try:
                conn.execute("ALTER TABLE messages ADD COLUMN user_id INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass

            conn.execute("CREATE INDEX IF NOT EXISTS idx_detected_at ON messages(detected_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_content_hash ON messages(content_hash)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sender ON messages(sender)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_user_id ON messages(user_id)")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_config (
                    user_id INTEGER PRIMARY KEY,
                    keywords TEXT DEFAULT '',
                    keyword_mode TEXT DEFAULT 'exact',
                    region_left INTEGER DEFAULT 0,
                    region_top INTEGER DEFAULT 0,
                    region_width INTEGER DEFAULT 800,
                    region_height INTEGER DEFAULT 600,
                    interval_seconds INTEGER DEFAULT 5,
                    notification_enabled INTEGER DEFAULT 1,
                    save_screenshots INTEGER DEFAULT 0,
                    group_name TEXT DEFAULT '默认'
                )
            """)

    # ---- User management ----

    def create_user(self, username, password):
        pw_hash = hashlib.sha256(password.encode()).hexdigest()
        try:
            with self._connect() as conn:
                c = conn.execute(
                    "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                    (username, pw_hash),
                )
                user_id = c.lastrowid
                conn.execute(
                    "INSERT OR IGNORE INTO user_config (user_id, keywords) VALUES (?, ?)",
                    (user_id, '考试,考核,测验,作业,截止日期,提交,考试时间,试卷,成绩,期末,期中,补考,答辩,实验报告,签到,点名'),
                )
                return user_id
        except sqlite3.IntegrityError:
            return None

    def verify_user(self, username, password):
        pw_hash = hashlib.sha256(password.encode()).hexdigest()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, username FROM users WHERE username=? AND password_hash=?",
                (username, pw_hash),
            ).fetchone()
            return dict(row) if row else None

    def user_exists(self, username):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM users WHERE username=?", (username,)
            ).fetchone()
            return row is not None

    # ---- User config ----

    def get_user_config(self, user_id):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM user_config WHERE user_id=?", (user_id,)
            ).fetchone()
            if not row:
                return {
                    'keywords': '',
                    'keyword_mode': 'exact',
                    'region': {'left': 0, 'top': 0, 'width': 800, 'height': 600},
                    'interval_seconds': 5,
                    'notification_enabled': True,
                    'save_screenshots': False,
                    'group_name': '默认',
                }
            r = dict(row)
            return {
                'keywords': r.get('keywords', ''),
                'keyword_mode': r.get('keyword_mode', 'exact'),
                'region': {
                    'left': r.get('region_left', 0),
                    'top': r.get('region_top', 0),
                    'width': r.get('region_width', 800),
                    'height': r.get('region_height', 600),
                },
                'interval_seconds': r.get('interval_seconds', 5),
                'notification_enabled': bool(r.get('notification_enabled', 1)),
                'save_screenshots': bool(r.get('save_screenshots', 0)),
                'group_name': r.get('group_name', '默认'),
            }

    def save_user_config(self, user_id, data):
        with self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO user_config
                (user_id, keywords, keyword_mode, region_left, region_top,
                 region_width, region_height, interval_seconds,
                 notification_enabled, save_screenshots, group_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                data.get('keywords', ''),
                data.get('keyword_mode', 'exact'),
                data.get('region', {}).get('left', 0),
                data.get('region', {}).get('top', 0),
                data.get('region', {}).get('width', 800),
                data.get('region', {}).get('height', 600),
                data.get('interval_seconds', 5),
                1 if data.get('notification_enabled', True) else 0,
                1 if data.get('save_screenshots', False) else 0,
                data.get('group_name', '默认'),
            ))

    # ---- Messages ----

    def insert_message(self, data):
        with self._connect() as conn:
            c = conn.execute(
                "INSERT INTO messages (user_id, detected_at, sender, content, "
                "matched_keywords, group_name, screenshot_path, content_hash) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (data.get('user_id', 0),
                 data.get('timestamp', datetime.now().isoformat()),
                 data.get('sender', '未知'),
                 data.get('content', ''),
                 ','.join(data.get('matched_keywords', [])),
                 data.get('group_name', '默认'),
                 data.get('screenshot_path'),
                 data.get('content_hash')),
            )
            return c.lastrowid

    def query_messages(self, user_id=None, keyword=None, sender=None,
                       start_date=None, end_date=None, limit=100, offset=0):
        conditions = []
        params = []
        if user_id:
            conditions.append("messages.user_id = ?")
            params.append(user_id)
        if keyword:
            conditions.append("messages.matched_keywords LIKE ?")
            params.append(f'%{keyword}%')
        if sender:
            conditions.append("messages.sender LIKE ?")
            params.append(f'%{sender}%')
        if start_date:
            conditions.append("messages.detected_at >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("messages.detected_at <= ?")
            params.append(end_date)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        sql = f"SELECT messages.*, users.username FROM messages LEFT JOIN users ON messages.user_id = users.id {where} ORDER BY messages.detected_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def mark_read(self, msg_id):
        with self._connect() as conn:
            conn.execute("UPDATE messages SET is_read=1 WHERE id=?", (msg_id,))

    def delete_message(self, msg_id):
        with self._connect() as conn:
            conn.execute("DELETE FROM messages WHERE id=?", (msg_id,))

    def clear_all(self, user_id=None):
        with self._connect() as conn:
            if user_id:
                conn.execute("DELETE FROM messages WHERE user_id=?", (user_id,))
            else:
                conn.execute("DELETE FROM messages")

    def get_unique_senders(self, user_id=None):
        with self._connect() as conn:
            if user_id:
                rows = conn.execute(
                    "SELECT DISTINCT sender FROM messages WHERE user_id=? ORDER BY sender",
                    (user_id,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT DISTINCT sender FROM messages ORDER BY sender"
                ).fetchall()
        return [r['sender'] for r in rows]

    def get_unique_keywords(self, user_id=None):
        with self._connect() as conn:
            if user_id:
                rows = conn.execute(
                    "SELECT matched_keywords FROM messages WHERE user_id=?", (user_id,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT matched_keywords FROM messages").fetchall()
        kw_set = set()
        for r in rows:
            for kw in r['matched_keywords'].split(','):
                kw = kw.strip()
                if kw:
                    kw_set.add(kw)
        return sorted(kw_set)

    def get_statistics(self, user_id=None):
        with self._connect() as conn:
            if user_id:
                total = conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE user_id=?", (user_id,)
                ).fetchone()[0]
                senders = conn.execute(
                    "SELECT sender, COUNT(*) as cnt FROM messages "
                    "WHERE user_id=? GROUP BY sender ORDER BY cnt DESC LIMIT 10",
                    (user_id,)
                ).fetchall()
                kw_rows = conn.execute(
                    "SELECT matched_keywords FROM messages WHERE user_id=?", (user_id,)
                ).fetchall()
            else:
                total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
                senders = conn.execute(
                    "SELECT sender, COUNT(*) as cnt FROM messages "
                    "GROUP BY sender ORDER BY cnt DESC LIMIT 10"
                ).fetchall()
                kw_rows = conn.execute(
                    "SELECT matched_keywords FROM messages"
                ).fetchall()
        kw_count = {}
        for r in kw_rows:
            for kw in r['matched_keywords'].split(','):
                kw = kw.strip()
                if kw:
                    kw_count[kw] = kw_count.get(kw, 0) + 1
        return {
            'total': total,
            'top_senders': [dict(s) for s in senders],
            'keyword_counts': sorted(kw_count.items(), key=lambda x: x[1], reverse=True),
        }

    def export_csv(self, path, user_id=None):
        with self._connect() as conn:
            if user_id:
                rows = conn.execute(
                    "SELECT * FROM messages WHERE user_id=? ORDER BY detected_at DESC",
                    (user_id,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM messages ORDER BY detected_at DESC"
                ).fetchall()
        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['ID', '用户ID', '检测时间', '发送者', '内容', '匹配关键词', '群名', '已读'])
            for r in rows:
                writer.writerow([r['id'], r['user_id'], r['detected_at'], r['sender'],
                                 r['content'], r['matched_keywords'],
                                 r['group_name'], r['is_read']])
