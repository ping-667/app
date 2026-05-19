"""OneBot 11 WebSocket client — connects to NapCatQQ / LLOneBot and
receives message events in real time.

Compatible with:
  - NapCatQQ  (ws://127.0.0.1:3001)
  - LLOneBot  (ws://127.0.0.1:3001)
  - Any OneBot 11 compliant WebSocket server

Protocol ref: https://github.com/botuniverse/onebot-11
"""

from __future__ import annotations

import json
import time
import queue
import threading
import logging

import websocket

logger = logging.getLogger(__name__)


class OneBotClient:
    """Connect to a OneBot 11 WebSocket server, receive message events.

    Uses *forward* WebSocket mode: the bot (NapCat/LLOneBot) listens,
    we connect to it.

    Usage:
        client = OneBotClient("ws://127.0.0.1:3001")
        client.start()
        while True:
            msg = client.get_message(timeout=5)
            if msg:
                process(msg)
    """

    def __init__(self, ws_url="ws://127.0.0.1:3001", group_name=None):
        self.ws_url = ws_url
        self.group_name = group_name
        self._running = threading.Event()
        self._thread = None
        self._msg_queue = queue.Queue()
        self._connected = threading.Event()

    @property
    def connected(self):
        return self._connected.is_set()

    def start(self):
        if self._running.is_set():
            return
        self._running.set()
        self._thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._thread.start()
        logger.info(f"OneBot 客户端启动, 目标: {self.ws_url}")

    def stop(self):
        self._running.clear()
        if self._thread:
            self._thread.join(timeout=3.0)
        logger.info("OneBot 客户端已停止")

    def get_message(self, timeout=1.0):
        """Pop one parsed message dict, or None if queue empty."""
        try:
            return self._msg_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    # ------------------------------------------------------------------
    # WebSocket receive loop
    # ------------------------------------------------------------------

    def _recv_loop(self):
        ws = None
        backoff = 2

        while self._running.is_set():
            try:
                ws = websocket.create_connection(
                    self.ws_url,
                    timeout=3,
                    enable_multithread=True,
                )
                self._connected.set()
                logger.info(f"已连接到 OneBot WS: {self.ws_url}")
                backoff = 2

                while self._running.is_set():
                    try:
                        raw = ws.recv()
                    except websocket.WebSocketTimeoutException:
                        # Timeout is normal — just means no messages in 3s
                        continue
                    if not raw:
                        continue
                    data = json.loads(raw)
                    logger.info(f"OneBot 收到原始事件: post_type={data.get('post_type')}, message_type={data.get('message_type')}")
                    parsed = self._parse_event(data)
                    if parsed:
                        self._msg_queue.put(parsed)

            except websocket.WebSocketTimeoutException:
                continue
            except Exception as e:
                logger.warning(f"OneBot 异常: {e}")
                self._connected.clear()
                if ws:
                    try:
                        ws.close()
                    except Exception:
                        pass
                logger.warning(
                    f"OneBot 连接断开，{backoff}s 后重连..."
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)

    # ------------------------------------------------------------------
    # Event parser — OneBot 11 → internal message dict
    # ------------------------------------------------------------------

    def _parse_event(self, data: dict) -> dict | None:
        if data.get("post_type") != "message":
            return None

        msg_type = data.get("message_type", "")
        if msg_type not in ("group", "private"):
            return None

        sender_data = data.get("sender", {})
        sender = sender_data.get("card") or sender_data.get("nickname") or "未知"

        raw = data.get("raw_message", "") or data.get("message", "")
        if isinstance(raw, list):
            text_parts = []
            for seg in raw:
                if isinstance(seg, dict):
                    if seg.get("type") == "text":
                        text_parts.append(seg.get("data", {}).get("text", ""))
                elif isinstance(seg, str):
                    text_parts.append(seg)
            content = "".join(text_parts)
        else:
            content = str(raw)

        if not content.strip():
            logger.info(f"OneBot 消息内容为空, 跳过: sender={sender}, msg_type={msg_type}")
            return None

        if msg_type == "group":
            group_name = data.get("group_name", "") or str(data.get("group_id", ""))
            logger.info(f"OneBot 群消息: group_name={group_name}, sender={sender}, content={content[:60]}")
            if self.group_name and self.group_name != "默认":
                if self.group_name not in str(group_name):
                    logger.info(f"OneBot 群名不匹配: '{self.group_name}' not in '{group_name}', 跳过")
                    return None
        else:
            group_name = f"私聊-{sender}"
            logger.info(f"OneBot 私聊消息: sender={sender}, content={content[:60]}")

        return {
            "sender": sender,
            "content": content,
            "matched_keywords": [],
            "full_text": content,
            "group_name": str(group_name),
            "message_type": msg_type,
            "data": data,
        }

    # ------------------------------------------------------------------
    # Heartbeat / status
    # ------------------------------------------------------------------

    def get_status(self):
        return {
            "connected": self._connected.is_set(),
            "ws_url": self.ws_url,
            "queue_size": self._msg_queue.qsize(),
        }
