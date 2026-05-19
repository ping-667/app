import os
import time
import queue
import threading
import logging
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image
import mss
import win32gui
import win32con
import win32process
import psutil

logger = logging.getLogger(__name__)

# Known QQ window class names across different QQ versions
QQ_PROCESS_NAMES = {"qq.exe", "qqnt.exe", "tim.exe"}

# Class names that are ONLY used by QQ (not generic Chromium/Qt)
QQ_ONLY_CLASSES = {
    "TXGuiFoundation",         # Classic QQ / TIM — unique to QQ
}

# Class names that need process name verification (shared with other apps)
QQ_SHARED_CLASSES = {
    "Chrome_WidgetWin_0",      # Chromium CEF — used by QQ, VS Code, Edge, etc.
    "Chrome_WidgetWin_1",
    "Qt5152QWindowIcon",       # Qt — used by QQ and other Qt apps
    "Qt5152QWindowToolSaveBits",
}


class Monitor:
    """Background monitoring: find QQ window → briefly raise → screenshot → restore.

    Strategy:
      1. Scan all top-level windows for QQ (by class name / process name / title)
      2. Briefly raise QQ to top-most (SWP_NOACTIVATE, no focus steal)
      3. Screenshot the window area via MSS
      4. Restore QQ's Z-order immediately
      5. OCR → keyword detect → notify

    This works even when QQ is covered by other windows or minimized.
    """

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
        self._logged_windows = False  # only log window list once

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
    # Find QQ window — process name + class name + title matching
    # ------------------------------------------------------------------

    def _get_process_name(self, hwnd):
        try:
            _pid = win32process.GetWindowThreadProcessId(hwnd)[1]
            proc = psutil.Process(_pid)
            return proc.name().lower()
        except Exception:
            return ""

    def _find_qq_hwnd(self, group_name=None):
        """Enumerate top-level windows, find QQ by class / process / title.
        Returns (hwnd, rect) or (None, None)."""
        candidates = []

        def _enum(hwnd, _lparam):
            title = win32gui.GetWindowText(hwnd)
            cls = win32gui.GetClassName(hwnd)
            if not title or len(title) < 1:
                return True
            proc = self._get_process_name(hwnd)
            is_qq_proc = proc in QQ_PROCESS_NAMES

            # ---- Unique QQ class (TXGuiFoundation) — no process check needed ----
            if cls in QQ_ONLY_CLASSES:
                candidates.append(("unique_class", hwnd, title, cls, proc))
                return True

            # ---- Shared class (Chrome/Qt) — must verify process name ----
            if cls in QQ_SHARED_CLASSES and is_qq_proc:
                candidates.append(("shared_class", hwnd, title, cls, proc))
                return True

            # ---- QQ process name (any class) ----
            if is_qq_proc and title and len(title) >= 1:
                candidates.append(("process", hwnd, title, cls, proc))
                return True

            # ---- Title contains QQ keywords (fallback) ----
            if title and any(k in title for k in ("QQ", "TIM", "腾讯", "qq")):
                candidates.append(("title", hwnd, title, cls, proc))
                return True

            return True

        win32gui.EnumWindows(_enum, None)

        # Log ALL windows on first run (helps debug)
        if not self._logged_windows:
            self._logged_windows = True
            qq_like = []
            def _debug_enum(hwnd, _lp):
                t = win32gui.GetWindowText(hwnd)
                c = win32gui.GetClassName(hwnd)
                p = self._get_process_name(hwnd)
                if t and len(t) >= 2:
                    qq_like.append((t[:40], c, p))
                return True
            win32gui.EnumWindows(_debug_enum, None)
            logger.info(f"系统共有 {len(qq_like)} 个可见窗口（含QQ相关进程窗口）")
            # Log any window with QQ-related process name
            qq_procs = [(t, c, p) for t, c, p in qq_like
                        if any(k in p for k in ("qq", "tim", "tx", "tencent"))]
            if qq_procs:
                logger.info(f"QQ相关进程窗口: {qq_procs}")
            else:
                logger.warning("未发现QQ相关进程窗口，请确认QQ正在运行")
                # Log some sample windows for debugging
                sample = [(t, c, p) for t, c, p in qq_like
                          if t and len(t) > 3][:15]
                logger.info(f"窗口采样: {sample}")

        # Prefer windows matching group name, but don't discard others.
        # The group name may not appear in the window title (e.g. QQNT
        # tabs), so non-matching candidates remain as fallback.
        if group_name and group_name != "默认":
            matching = [
                (k, h, t, c, p) for k, h, t, c, p in candidates
                if group_name in t
            ]
            if matching:
                candidates = matching
                logger.info(f"群名'{group_name}'匹配 {len(matching)} 个窗口")
            else:
                logger.info(
                    f"群名'{group_name}'未匹配任何窗口标题，使用全部 {len(candidates)} 个候选")

        if not candidates:
            return None, None

        # Filter: skip tiny/off-screen windows (QQ helper windows, tray icons, etc.)
        def _is_plausible(hwnd):
            r = win32gui.GetWindowRect(hwnd)
            w, h = r[2] - r[0], r[3] - r[1]
            # Must be reasonable size AND not at extreme off-screen coords
            if w < 200 or h < 200:
                return False
            if r[0] < -10000 or r[1] < -10000:
                return False
            return True

        # Priority: unique_class > shared_class > process > title
        # Sort by area (largest first) within each priority group
        for kind in ("unique_class", "shared_class", "process"):
            group = [(hwnd, title, cls, proc) for k, hwnd, title, cls, proc in candidates
                     if k == kind and _is_plausible(hwnd)]
            if group:
                group.sort(key=lambda x: (
                    win32gui.GetWindowRect(x[0])[2] - win32gui.GetWindowRect(x[0])[0]
                ) * (win32gui.GetWindowRect(x[0])[3] - win32gui.GetWindowRect(x[0])[1]),
                reverse=True)
                hwnd, title, cls, proc = group[0]
                rect = win32gui.GetWindowRect(hwnd)
                logger.info(f"找到QQ窗口({kind}): title='{title}' rect={rect}")
                return hwnd, rect

        for kind, hwnd, title, cls, proc in candidates:
            if _is_plausible(hwnd):
                rect = win32gui.GetWindowRect(hwnd)
                logger.info(f"找到QQ窗口(title): '{title}' rect={rect}")
                return hwnd, rect

        return None, None

    # ------------------------------------------------------------------
    # Capture — region mode (fallback)
    # ------------------------------------------------------------------

    def _get_region_dict(self):
        if hasattr(self.config, "get_region_dict"):
            return self.config.get_region_dict()
        r = self.config.get("region", {})
        return {
            "left": int(r.get("left", 0)),
            "top": int(r.get("top", 0)),
            "width": int(r.get("width", 800)),
            "height": int(r.get("height", 600)),
        }

    def _capture_region(self):
        region = self._get_region_dict()
        if region["width"] < 50 or region["height"] < 50:
            return None
        with mss.MSS() as sct:
            img = sct.grab(region)
            return Image.frombytes("RGB", img.size, img.rgb)

    # ------------------------------------------------------------------
    # Capture — window mode (top-most + MSS, for background QQ)
    # ------------------------------------------------------------------

    def _capture_window_topmost(self, hwnd):
        """Briefly raise QQ to top-most → screenshot → restore. No activation.

        Tries PrintWindow first (captures window content directly), falls back
        to MSS screen capture for GPU-rendered windows where PrintWindow returns black.
        """
        try:
            rect = win32gui.GetWindowRect(hwnd)
            left, top, right, bottom = rect
            w, h = right - left, bottom - top
            if w < 100 or h < 100:
                logger.debug(f"QQ窗口太小: {w}x{h}")
                return None

            fore_hwnd = win32gui.GetForegroundWindow()
            was_minimized = win32gui.IsIconic(hwnd)

            if was_minimized:
                win32gui.ShowWindow(hwnd, win32con.SW_SHOWNOACTIVATE)
                time.sleep(0.15)

            # Raise to top-most without stealing focus
            win32gui.SetWindowPos(
                hwnd, win32con.HWND_TOPMOST,
                left, top, w, h,
                win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW,
            )
            time.sleep(0.3)  # Allow DWM to composite the window content

            pil_img = self._capture_printwindow(hwnd, w, h)
            if pil_img is not None and self._is_likely_blank(pil_img):
                pil_img = None  # PrintWindow returned black, try MSS instead
            if pil_img is None:
                with mss.MSS() as sct:
                    region = {"left": left, "top": top, "width": w, "height": h}
                    img = sct.grab(region)
                    pil_img = Image.frombytes("RGB", img.size, img.rgb)

            # Restore
            win32gui.SetWindowPos(
                hwnd, win32con.HWND_NOTOPMOST,
                left, top, w, h,
                win32con.SWP_NOACTIVATE | win32con.SWP_NOMOVE | win32con.SWP_NOSIZE,
            )

            if was_minimized:
                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)

            if fore_hwnd and fore_hwnd != hwnd:
                try:
                    win32gui.SetForegroundWindow(fore_hwnd)
                except Exception:
                    pass

            return pil_img
        except Exception:
            return None

    def _capture_printwindow(self, hwnd, w, h):
        """Try PrintWindow — direct window content capture.

        Returns PIL Image on success, None if the method is unsupported.
        For GPU-rendered (Electron/CEF) windows this often returns black,
        so callers should verify the result.
        """
        try:
            import win32ui as w32ui

            hwnd_dc = win32gui.GetWindowDC(hwnd)
            mfc_dc = w32ui.CreateDCFromHandle(hwnd_dc)
            save_dc = mfc_dc.CreateCompatibleDC()
            bitmap = w32ui.CreateBitmap()
            bitmap.CreateCompatibleBitmap(mfc_dc, w, h)
            save_dc.SelectObject(bitmap)

            # PW_RENDERFULLCONTENT = 2 (try to get full content, not just visible)
            ok = win32gui.PrintWindow(hwnd, save_dc.GetSafeHdc(), 2)
            if not ok:
                # Retry with PW_CLIENTONLY = 1
                ok = win32gui.PrintWindow(hwnd, save_dc.GetSafeHdc(), 1)

            if ok:
                bmp_info = bitmap.GetInfo()
                bmp_str = bitmap.GetBitmapBits(True)
                return Image.frombuffer(
                    "RGB",
                    (bmp_info["bmWidth"], bmp_info["bmHeight"]),
                    bmp_str, "raw", "BGRX", 0, 1,
                )
        except Exception:
            pass
        finally:
            try:
                save_dc.DeleteDC()
                mfc_dc.DeleteDC()
                win32gui.ReleaseDC(hwnd, hwnd_dc)
            except Exception:
                pass
        return None

    def _is_likely_blank(self, pil_img, threshold=0.98):
        """Check if an image is mostly uniform (likely blank/black)."""
        try:
            arr = np.array(pil_img.resize((50, 50)).convert("L"))
            _, counts = np.unique(arr, return_counts=True)
            return counts.max() / counts.sum() >= threshold
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Capture — UIA text extraction (invisible, works minimized/hidden)
    # ------------------------------------------------------------------

    def _ensure_com_initialized(self):
        """Initialize COM on this thread (lazy, idempotent)."""
        if not getattr(self, "_com_initialized", False):
            import pythoncom
            pythoncom.CoInitialize()
            self._com_initialized = True

    def _uninit_com(self):
        if getattr(self, "_com_initialized", False):
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception:
                pass
            self._com_initialized = False

    def _capture_via_uia(self, hwnd):
        """Extract text from QQ window via UI Automation.

        Works even when the window is minimized or completely hidden —
        no screenshot needed, no window manipulation.

        Returns list of dicts: {'text', 'confidence', 'y_center', 'bbox'}
        compatible with OCR output format.
        """
        try:
            self._ensure_com_initialized()
            import uiautomation as auto

            element = auto.ControlFromHandle(hwnd)
            if not element:
                logger.debug("UIA: 无法获取窗口控件")
                return []

            texts = []
            self._walk_uia_tree(element, texts, depth=0)

            if not texts:
                logger.debug("UIA: 未提取到文本")
                return []

            # Remove duplicates (same text at same position)
            seen = set()
            result = []
            for item in texts:
                key = (item["text"], item["y_center"])
                if key not in seen:
                    seen.add(key)
                    result.append(item)

            result.sort(key=lambda x: x["y_center"])
            logger.info(
                f"UIA提取到 {len(result)} 个文本元素 "
                f"(原始 {len(texts)} 个)"
            )
            # Log a sample of extracted text for debugging
            sample = [r["text"][:40] for r in result[:10]]
            logger.info(f"UIA文本采样: {sample}")
            return result
        except Exception:
            logger.error("UIA文本提取失败", exc_info=True)
            return []

    def _walk_uia_tree(self, element, results, depth, max_depth=20):
        """Recursively walk UIA tree, collecting text leaf nodes."""
        if depth > max_depth:
            return
        try:
            name = element.Name
            # Only collect meaningful text (skip single chars unless CJK)
            if name and len(name.strip()) >= 1:
                name = name.strip()
                # Skip pure numbers shorter than 5 chars (likely IDs, not messages)
                if name.isdigit() and len(name) < 5:
                    pass
                elif len(name) >= 2 or ord(name[0]) > 127:
                    try:
                        rect = element.BoundingRectangle
                        y_center = int((rect.top + rect.bottom) / 2) if rect else 0
                        results.append({
                            "text": name,
                            "confidence": 0.95,
                            "y_center": y_center,
                            "bbox": [
                                [rect.left, rect.top],
                                [rect.right, rect.top],
                                [rect.right, rect.bottom],
                                [rect.left, rect.bottom],
                            ] if rect else [[0, 0], [0, 0], [0, 0], [0, 0]],
                        })
                    except Exception:
                        pass
        except Exception:
            pass

        try:
            children = element.GetChildren()
            for child in children:
                self._walk_uia_tree(child, results, depth + 1, max_depth)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Similarity check
    # ------------------------------------------------------------------

    def _should_skip_ocr(self, current, threshold=0.95):
        if self._last_image is None:
            return False
        try:
            thumb = (100, 100)
            a = np.array(self._last_image.resize(thumb).convert("L"))
            b = np.array(current.resize(thumb).convert("L"))
            return np.mean(a == b) >= threshold
        except Exception:
            return False

    # ------------------------------------------------------------------
    # OneBot WebSocket loop
    # ------------------------------------------------------------------

    def _loop_onebot(self, interval, group_name):
        """Event-driven loop: receive messages from OneBot (NapCat/LLOneBot)."""
        ws_url = self.config.get("ws_url", "ws://127.0.0.1:3001")
        from onebot_client import OneBotClient

        client = OneBotClient(ws_url, group_name=group_name)
        client.start()
        logger.info(
            f"OneBot WS 模式已启动 (ws_url={ws_url}, group={group_name})"
        )

        last_status_log = time.time()

        while self._running.is_set():
            msg = client.get_message(timeout=1.0)
            if msg is None:
                # Periodic status heartbeat
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
                    f"OneBot 检测到关键词: {result['matched_keywords']} "
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
                    f"OneBot消息未命中关键词: sender={sender} "
                    f"content={content[:80]}..."
                )

        client.stop()
        logger.warning("OneBot 监控循环已退出")

    # ------------------------------------------------------------------
    # Main loop (screenshot / UIA)
    # ------------------------------------------------------------------

    def _loop(self):
        interval = self.config.get("interval_seconds", 5)
        diff_threshold = self.config.get("image_diff_threshold", 0.95)
        group_name = self.config.get("group_name", "默认")
        capture_mode = self.config.get("capture_mode", "screenshot")
        logger.info(
            f"后台监控启动 (interval={interval}s, group={group_name}, "
            f"capture_mode={capture_mode})"
        )

        # ---- OneBot WebSocket path (event-driven, no screenshot/OCR) ----
        if capture_mode == "onebot_ws":
            self._loop_onebot(interval, group_name)
            return

        _mode = "window"       # current mode: "window" or "region"
        _no_win_count = 0
        _capture_fail_count = 0
        _uia_load_warned = False  # warn once if UIA import fails

        try:
            while self._running.is_set():
                try:
                    self._capture_count += 1
                    self._last_capture_time = datetime.now().isoformat()

                    if self._capture_count % 10 == 1:
                        logger.info(
                            f"心跳: capture #{self._capture_count}, "
                            f"mode={_mode}, capture_mode={capture_mode}"
                        )
                    pil_img = None
                    ocr_results = None  # set directly by UIA path

                    if _mode == "window":
                        hwnd, _rect = self._find_qq_hwnd(group_name)
                        if hwnd is None:
                            _no_win_count += 1
                            if _no_win_count == 1:
                                logger.warning(
                                    "未找到QQ窗口，请确认QQ已打开。"
                                    "将尝试使用区域模式..."
                                )
                            if _no_win_count >= 5:
                                if capture_mode == "uia":
                                    logger.warning(
                                        "UIA模式需要QQ窗口句柄，"
                                        "无法回退到区域模式，继续尝试..."
                                    )
                                    _no_win_count = 3  # keep retrying
                                else:
                                    region = self._get_region_dict()
                                    logger.info(
                                        f"切换至区域截屏模式 "
                                        f"(left={region['left']}, top={region['top']}, "
                                        f"{region['width']}x{region['height']})"
                                    )
                                    _mode = "region"
                            time.sleep(interval)
                            continue
                        _no_win_count = 0

                        # ---- UIA path (invisible, no window manipulation) ----
                        if capture_mode == "uia":
                            ocr_results = self._capture_via_uia(hwnd)
                            if ocr_results is None:
                                ocr_results = []
                            if not ocr_results:
                                logger.debug(
                                    f"UIA未提取到文本 "
                                    f"(capture #{self._capture_count})"
                                )
                                time.sleep(interval)
                                continue
                            logger.info(
                                f"UIA提取到 {len(ocr_results)} 个文本元素"
                            )

                        # ---- Screenshot path ----
                        else:
                            pil_img = self._capture_window_topmost(hwnd)
                            if pil_img is None:
                                _capture_fail_count += 1
                                time.sleep(interval)
                                continue
                            _capture_fail_count = 0

                    else:  # region mode (screenshot only)
                        pil_img = self._capture_region()
                        if pil_img is None:
                            time.sleep(interval)
                            continue
                        # Periodically re-check if QQ window appears
                        _no_win_count += 1
                        if _no_win_count >= 10:
                            hwnd, _rect = self._find_qq_hwnd(group_name)
                            if hwnd is not None:
                                logger.info("检测到QQ窗口，切回窗口模式")
                                _mode = "window"
                                _no_win_count = 0
                                if capture_mode == "uia":
                                    ocr_results = self._capture_via_uia(hwnd)
                                    if not ocr_results:
                                        time.sleep(interval)
                                        continue
                                else:
                                    pil_img = self._capture_window_topmost(hwnd)
                                    if pil_img is None:
                                        time.sleep(interval)
                                        continue

                    # ---- Image dedup + OCR (screenshot path only) ----
                    if pil_img is not None:
                        if self._should_skip_ocr(pil_img, diff_threshold):
                            if self._capture_count % 3 != 0:
                                logger.debug(f"跳过相似帧 #{self._capture_count}")
                                time.sleep(interval)
                                continue
                            logger.info(f"强制OCR (每3帧一次) #{self._capture_count}")

                        _t0 = time.time()
                        ocr_results = self.ocr.recognize(pil_img)
                        _ocr_cost = time.time() - _t0
                        if not ocr_results:
                            logger.info(
                                f"OCR未识别到文字 (capture #{self._capture_count}, "
                                f"耗时 {_ocr_cost:.1f}s)"
                            )
                            time.sleep(interval)
                            continue
                        logger.info(
                            f"OCR识别到 {len(ocr_results)} 个文本块"
                            f" (耗时 {_ocr_cost:.1f}s)"
                        )

                    # ---- Keyword detection (common path for both modes) ----
                    if ocr_results:
                        result = self.detector.process_ocr_result(ocr_results)
                        if result:
                            logger.info(
                                f"检测到关键词: {result['matched_keywords']} "
                                f"发送者: {result['sender']}"
                            )
                            self._save_and_notify(result, pil_img)
                        else:
                            logger.info(
                                f"文本未命中关键词 "
                                f"(capture #{self._capture_count})"
                            )

                    if pil_img is not None:
                        self._last_image = pil_img.copy()

                except Exception:
                    logger.error("监控循环异常", exc_info=True)

                time.sleep(interval)

        finally:
            self._uninit_com()
            logger.warning("监控循环已退出")

    # ------------------------------------------------------------------
    # Save & notify
    # ------------------------------------------------------------------

    def _save_and_notify(self, result, image=None):
        timestamp = datetime.now().isoformat()
        result["timestamp"] = timestamp
        result["user_id"] = self.user_id
        result["group_name"] = self.config.get("group_name", "默认")

        if self.config.get("save_screenshots", False) and image:
            ss_dir = Path(os.getenv("APPDATA")) / "QQMonitor" / "screenshots"
            ss_dir.mkdir(parents=True, exist_ok=True)
            ss_path = ss_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
            image.save(str(ss_path))
            result["screenshot_path"] = str(ss_path)

        self._detection_count += 1
        row_id = self.db.insert_message(result)
        result["db_id"] = row_id

        if self.config.get("notification_enabled", True):
            self._send_notification(result)

        self._result_queue.put(result)

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
