import re
import hashlib
import time
from collections import deque


class Detector:
    def __init__(self, keywords, keyword_mode='exact'):
        self.keywords = [k for k in keywords if k and k.strip()]
        self.keyword_mode = keyword_mode
        self._recent_hashes = deque(maxlen=300)

    def set_keywords(self, keywords):
        self.keywords = [k for k in keywords if k and k.strip()]

    def parse_sender(self, ocr_lines):
        if not ocr_lines:
            return None

        time_patterns = [
            r'\d{4}[/\-.]\d{1,2}[/\-.]\d{1,2}\s*\d{1,2}:\d{2}(:\d{2})?',
            r'\[\d{1,2}:\d{2}(:\d{2})?\]',
            r'\d{1,2}:\d{2}(:\d{2})?',
            r'(上午|下午|凌晨|中午)\s*\d{1,2}:\d{2}',
            r'昨天|今天|前天',
        ]

        sender_line = None
        for i, line in enumerate(ocr_lines[:3]):
            text = line['text']
            for tp in time_patterns:
                if re.search(tp, text):
                    sender_line = text
                    break
            if sender_line:
                break

        if sender_line:
            for tp in time_patterns:
                sender_line = re.sub(tp, '', sender_line).strip()
            sender_line = re.sub(r'[\(\（\[\<].*?[\)\）\]\>]', '', sender_line).strip()
            sender_line = re.sub(r'[^一-鿿\w\s]', '', sender_line).strip()
            if 1 <= len(sender_line) <= 30:
                return sender_line
            return None

        for line in ocr_lines[:2]:
            text = line['text'].strip()
            if 1 <= len(text) <= 25 and not any(
                    text.startswith(w) for w in ['消息', '系统', '通知', '群', '退回']):
                return text
        return None

    def match_keywords(self, text):
        matched = []
        for kw in self.keywords:
            if not kw or not kw.strip():
                continue
            if self.keyword_mode == 'regex':
                try:
                    if re.search(kw, text, re.IGNORECASE):
                        matched.append(kw)
                except re.error:
                    if kw.lower() in text.lower():
                        matched.append(kw)
            else:
                if kw.lower() in text.lower():
                    matched.append(kw)
        return matched

    def is_duplicate(self, content, sender, window_seconds=60):
        normalized = re.sub(r'\s+', '', content.lower())
        normalized = re.sub(r'[^一-鿿\w]', '', normalized)
        msg_hash = hashlib.sha256(
            f"{sender}|||{normalized}".encode()).hexdigest()

        now = time.time()
        for h, ts in list(self._recent_hashes):
            if now - ts > window_seconds:
                self._recent_hashes.remove((h, ts))

        for h, ts in self._recent_hashes:
            if h == msg_hash:
                return True
        self._recent_hashes.append((msg_hash, now))
        return False

    def process_ocr_result(self, ocr_lines):
        high_conf = [l for l in ocr_lines if l['confidence'] > 0.5]
        if not high_conf:
            return None

        full_text = '\n'.join(l['text'] for l in high_conf)
        sender = self.parse_sender(high_conf)
        matched = self.match_keywords(full_text)
        if not matched:
            return None
        if self.is_duplicate(full_text, sender or '未知'):
            return None

        body_lines = []
        for l in high_conf:
            if sender and l['text'].strip() == sender:
                continue
            body_lines.append(l['text'])
        body = '\n'.join(body_lines).strip() or full_text.strip()

        return {
            'sender': sender or '未知',
            'content': body,
            'matched_keywords': matched,
            'full_text': full_text,
        }
