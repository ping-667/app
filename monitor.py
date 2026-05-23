import time
import queue
import threading
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class Monitor:
    """Background monitoring via OneBot WebSocket — receives QQ messages
    in real time from NapCatQQ / LLOneBot, matches keywords, saves to DB.
    """

    def __init__(self, config, detector, db):
        self.config = config
        self.detector = detector
        self.db = db
        self.user_id = 0
        self._running = threading.Event()
        self._thread = None
        self._result_queue = queue.Queue()
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
            "running": self._running.is_set(),
            "captures": self._capture_count,
            "detections": self._detection_count,
            "last_capture": self._last_capture_time,
        }

    # ------------------------------------------------------------------
    # Main loop — delegates to OneBot event-driven loop
    # ------------------------------------------------------------------

    def _loop(self):
        interval = self.config.get("interval_seconds", 5)
        group_name = self.config.get("group_name", "默认")
        ws_url = self.config.get("ws_url", "ws://127.0.0.1:3001")
        from onebot_client import OneBotClient

        client = OneBotClient(ws_url, group_name=group_name)
        client.start()
        logger.info(f"OneBot 监控启动 (ws_url={ws_url}, group={group_name})")

        last_status_log = time.time()

        while self._running.is_set():
            msg = client.get_message(timeout=1.0)
            if msg is None:
                if time.time() - last_status_log > 30:
                    logger.info(
                        f"OneBot 状态: connected={client.connected}, "
                        f"queue={client.get_status()['queue_size']}"
                    )
                    last_status_log = time.time()
                continue

            self._capture_count += 1
            self._last_capture_time = datetime.now().isoformat()

            content = msg.get("content", "")
            sender = msg.get("sender", "未知")

            result = self.detector.process_onebot_message(sender, content)
            if result:
                result["group_name"] = msg.get("group_name", group_name)
                result["message_type"] = msg.get("message_type", "")
                result["user_id"] = self.user_id
                result["timestamp"] = datetime.now().isoformat()
                logger.info(
                    f"检测到关键词: {result['matched_keywords']} "
                    f"发送者: {sender} 群: {result['group_name']}"
                )
                self._detection_count += 1
                row_id = self.db.insert_message(result)
                result["db_id"] = row_id
                if self.config.get("notification_enabled", True):
                    self._send_notification(result)
                self._result_queue.put(result)
            else:
                logger.info(
                    f"消息未命中关键词: sender={sender} "
                    f"content={content[:80]}..."
                )

        client.stop()
        logger.warning("OneBot 监控循环已退出")

    def _send_notification(self, result):
        try:
            from plyer import notification
            kws = ", ".join(result["matched_keywords"])
            body = result["content"][:80]
            if len(result["content"]) > 80:
                body += "..."
            notification.notify(
                title=f"QQ群提醒 - {result['sender']}",
                message=f"关键词: {kws}\n{body}",
                app_name="QQ群消息监控",
                timeout=10,
            )
        except Exception:
            logger.warning("发送通知失败", exc_info=True)
