import sqlite3
import os
import csv
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
        return conn

    def _init_schema(self):
        with self._connect() as conn:
            conn.executescript("""
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
                );
                CREATE INDEX IF NOT EXISTS idx_detected_at ON messages(detected_at);
                CREATE INDEX IF NOT EXISTS idx_content_hash ON messages(content_hash);
                CREATE INDEX IF NOT EXISTS idx_sender ON messages(sender);
                CREATE INDEX IF NOT EXISTS idx_keywords ON messages(matched_keywords);
            """)

    def insert_message(self, data):
        with self._connect() as conn:
            c = conn.execute(
                "INSERT INTO messages (detected_at, sender, content, matched_keywords, "
                "group_name, screenshot_path, content_hash) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (data.get('timestamp', datetime.now().isoformat()),
                 data.get('sender', '未知'),
                 data.get('content', ''),
                 ','.join(data.get('matched_keywords', [])),
                 data.get('group_name', '默认'),
                 data.get('screenshot_path'),
                 data.get('content_hash')),
            )
            return c.lastrowid

    def query_messages(self, keyword=None, sender=None, start_date=None,
                       end_date=None, limit=100, offset=0):
        conditions = []
        params = []
        if keyword:
            conditions.append("matched_keywords LIKE ?")
            params.append(f'%{keyword}%')
        if sender:
            conditions.append("sender LIKE ?")
            params.append(f'%{sender}%')
        if start_date:
            conditions.append("detected_at >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("detected_at <= ?")
            params.append(end_date)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        sql = f"SELECT * FROM messages {where} ORDER BY detected_at DESC LIMIT ? OFFSET ?"
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

    def clear_all(self):
        with self._connect() as conn:
            conn.execute("DELETE FROM messages")

    def get_unique_senders(self):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT sender FROM messages ORDER BY sender"
            ).fetchall()
        return [r['sender'] for r in rows]

    def get_unique_keywords(self):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT matched_keywords FROM messages"
            ).fetchall()
        kw_set = set()
        for r in rows:
            for kw in r['matched_keywords'].split(','):
                kw = kw.strip()
                if kw:
                    kw_set.add(kw)
        return sorted(kw_set)

    def get_statistics(self):
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            senders = conn.execute(
                "SELECT sender, COUNT(*) as cnt FROM messages "
                "GROUP BY sender ORDER BY cnt DESC LIMIT 10"
            ).fetchall()
            keywords = conn.execute(
                "SELECT matched_keywords FROM messages"
            ).fetchall()
        kw_count = {}
        for r in keywords:
            for kw in r['matched_keywords'].split(','):
                kw = kw.strip()
                if kw:
                    kw_count[kw] = kw_count.get(kw, 0) + 1
        return {
            'total': total,
            'top_senders': [dict(s) for s in senders],
            'keyword_counts': sorted(kw_count.items(), key=lambda x: x[1], reverse=True),
        }

    def export_csv(self, path):
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM messages ORDER BY detected_at DESC").fetchall()
        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['ID', '检测时间', '发送者', '内容', '匹配关键词', '群名', '已读'])
            for r in rows:
                writer.writerow([r['id'], r['detected_at'], r['sender'],
                                 r['content'], r['matched_keywords'],
                                 r['group_name'], r['is_read']])
