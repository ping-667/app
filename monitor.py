import time
import threading
import queue
import logging
from datetime import datetime

import numpy as np
from PIL import Image
from plyer import notification

logger = logging.getLogger(__name__)


class Monitor:
    def __init__(self, config, ocr_engine, detector, db):
        self.config = config
        self.ocr = ocr_engine
        self.detector = detector
        self.db = db
        self.user_id = 0
        self._running = threading.Event()
        self._thread = None
        self._result_queue = queue.Queue()
        self._last_image = None
        self._capture_count = 0
        self._detection_count = 0
        self._last_capture_time = None

    @property
    def result_queue(self):
        return self._result_queue

    @property
    def running(self):
        return self._running.is_set()

    def start(self):
        if self._running.is_set():
            return
        self._running.set()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("监控已启动")

    def stop(self):
        if not self._running.is_set():
            return
        self._running.clear()
        if self._thread:
            self._thread.join(timeout=3.0)
        logger.info("监控已停止")

    def get_status(self):
        return {
            'running': self._running.is_set(),
            'captures': self._capture_count,
            'detections': self._detection_count,
            'last_capture': self._last_capture_time,
        }

    def _loop(self):
        import mss
        interval = self.config.get('interval_seconds', 5)
        diff_threshold = self.config.get('image_diff_threshold', 0.95)

        with mss.mss() as sct:
            while self._running.is_set():
                try:
                    region = self.config.get_region_dict()
                    img = sct.grab(region)
                    pil_img = Image.frombytes('RGB', img.size, img.rgb)

                    if self._should_skip_ocr(pil_img, diff_threshold):
                        self._capture_count += 1
                        self._last_capture_time = datetime.now().isoformat()
                        time.sleep(interval)
                        continue

                    self._capture_count += 1
                    self._last_capture_time = datetime.now().isoformat()

                    ocr_results = self.ocr.recognize(pil_img)

                    result = self.detector.process_ocr_result(ocr_results)

                    if result:
                        self._save_and_notify(result, pil_img)

                    self._last_image = pil_img.copy()
                except Exception:
                    logger.error("监控循环异常", exc_info=True)
                    time.sleep(interval)

    def _should_skip_ocr(self, current, threshold):
        if self._last_image is None:
            return False
        thumb_size = (100, 100)
        a = np.array(self._last_image.resize(thumb_size).convert('L'))
        b = np.array(current.resize(thumb_size).convert('L'))
        similarity = np.mean(a == b)
        return similarity >= threshold

    def _save_and_notify(self, result, image):
        timestamp = datetime.now().isoformat()
        result['timestamp'] = timestamp
        result['user_id'] = self.user_id
        result['group_name'] = self.config.get('group_name', '默认')

        if self.config.get('save_screenshots', False):
            import os
            from pathlib import Path
            ss_dir = Path(os.getenv('APPDATA')) / 'QQMonitor' / 'screenshots'
            ss_dir.mkdir(parents=True, exist_ok=True)
            ss_path = ss_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
            image.save(str(ss_path))
            result['screenshot_path'] = str(ss_path)

        row_id = self.db.insert_message(result)
        result['db_id'] = row_id
        self._detection_count += 1

        if self.config.get('notification_enabled', True):
            self._send_notification(result)

        self._result_queue.put(result)

    def _send_notification(self, result):
        try:
            kws = ', '.join(result['matched_keywords'])
            body = result['content'][:80]
            if len(result['content']) > 80:
                body += '...'
            notification.notify(
                title=f"QQ群提醒 - {result['sender']}",
                message=f"关键词: {kws}\n{body}",
                app_name='QQ群消息监控',
                timeout=10,
            )
        except Exception:
            logger.warning("发送通知失败", exc_info=True)
