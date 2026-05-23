import json
import os
from pathlib import Path

DEFAULT_KEYWORDS = [
    "考试", "考核", "测验", "作业", "截止日期", "提交",
    "考试时间", "试卷", "成绩", "期末", "期中", "补考",
    "答辩", "实验报告", "查重", "预习", "签到", "点名",
]

DEFAULT_KEYWORDS_STR = ",".join(DEFAULT_KEYWORDS)

DEFAULT_CONFIG = {
    "interval_seconds": 5,
    "keywords": DEFAULT_KEYWORDS,
    "keyword_mode": "exact",
    "monitoring_enabled": True,
    "start_minimized": False,
    "notification_enabled": True,
    "group_name": "默认",
    "ws_url": "ws://127.0.0.1:3001",
}


class Config:
    def __init__(self):
        self.config_dir = Path(os.getenv("APPDATA")) / "QQMonitor"
        self.config_file = self.config_dir / "config.json"
        self.data: dict = {}

    def load(self):
        self.config_dir.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            loaded = {}
        self.data = {**DEFAULT_CONFIG, **loaded}

    def save(self):
        self.config_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.config_file.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        tmp.replace(self.config_file)

    def get(self, key, default=None):
        return self.data.get(key, DEFAULT_CONFIG.get(key, default))

    def set(self, key, value):
        self.data[key] = value
