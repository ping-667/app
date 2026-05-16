import os
import json
from pathlib import Path

DEFAULT_KEYWORDS = [
    '考试', '考核', '测验', '作业', '截止日期', '提交',
    '考试时间', '试卷', '成绩', '期末', '期中', '补考',
    '答辩', '实验报告', '查重', '预习', '签到', '点名',
]


class Config:
    def __init__(self):
        self.config_dir = Path(os.getenv('APPDATA')) / 'QQMonitor'
        self.config_file = self.config_dir / 'config.json'
        self.defaults = {
            'region': {'left': 0, 'top': 0, 'width': 800, 'height': 600},
            'interval_seconds': 5,
            'keywords': DEFAULT_KEYWORDS,
            'keyword_mode': 'exact',
            'monitoring_enabled': True,
            'start_minimized': False,
            'notification_enabled': True,
            'save_screenshots': False,
            'group_name': '默认',
            'image_diff_threshold': 0.95,
        }
        self.data = {}

    def load(self):
        self.config_dir.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            loaded = {}
        self.data = {**self.defaults, **loaded}

    def save(self):
        self.config_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.config_file.with_suffix('.tmp')
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        tmp.replace(self.config_file)

    def get(self, key, default=None):
        return self.data.get(key, self.defaults.get(key, default))

    def set(self, key, value):
        self.data[key] = value

    def get_region_dict(self):
        r = self.data['region']
        return {'left': int(r['left']), 'top': int(r['top']),
                'width': int(r['width']), 'height': int(r['height'])}
