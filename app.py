import base64
import io
import json
import os
import queue
import sys
import threading
import logging
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import Flask, render_template, request, jsonify, session, redirect, url_for

from utils import set_dpi_aware, setup_logging

set_dpi_aware()
logger = setup_logging("webapp")

app = Flask(__name__)
app.secret_key = "qq_monitor_fixed_secret_key_2026"
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

from database import Database
from ocr_engine import OCREngine
from detector import Detector
from monitor import Monitor
from config import DEFAULT_KEYWORDS_STR

db = Database()
ocr = OCREngine()

monitors: dict[int, Monitor] = {}
monitor_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.route("/login")
def login_page():
    return render_template("login.html")


@app.route("/")
@login_required
def index():
    return render_template("index.html")


@app.route("/region")
@login_required
def region_page():
    return render_template("region.html")


# ---------------------------------------------------------------------------
# Auth API
# ---------------------------------------------------------------------------

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json()
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username or not password:
        return jsonify({"ok": False, "error": "用户名和密码不能为空"})
    user = db.verify_user(username, password)
    if user:
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        return jsonify({"ok": True, "username": user["username"]})
    return jsonify({"ok": False, "error": "用户名或密码错误"})


@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json()
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if len(username) < 2:
        return jsonify({"ok": False, "error": "用户名至少2个字符"})
    if len(password) < 3:
        return jsonify({"ok": False, "error": "密码至少3个字符"})
    user_id = db.create_user(username, password)
    if user_id:
        session["user_id"] = user_id
        session["username"] = username
        return jsonify({"ok": True, "username": username})
    return jsonify({"ok": False, "error": "用户名已存在"})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Config API
# ---------------------------------------------------------------------------

@app.route("/api/config", methods=["GET"])
@login_required
def api_get_config():
    uid = session["user_id"]
    cfg = db.get_user_config(uid)
    r = cfg["region"]
    cfg["has_region"] = any([
        r["left"] != 0, r["top"] != 0,
        r["width"] != 800, r["height"] != 600,
    ])
    return jsonify(cfg)


@app.route("/api/config", methods=["POST"])
@login_required
def api_save_config():
    data = request.get_json()
    cfg = db.get_user_config(session["user_id"])
    for key in ("keywords", "keyword_mode", "interval_seconds", "group_name",
                "notification_enabled", "save_screenshots",
                "capture_mode", "ws_url"):
        if key in data:
            cfg[key] = data[key]
    if "region" in data:
        cfg["region"].update(data["region"])
    db.save_user_config(session["user_id"], cfg)

    # Sync keywords/mode to running monitor if they changed
    if "keywords" in data or "keyword_mode" in data:
        kws = _parse_keywords(cfg)
        mode = cfg.get("keyword_mode", "exact")
        _sync_monitor_detector(session["user_id"], kws, mode)

    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Keywords API
# ---------------------------------------------------------------------------

def _parse_keywords(cfg: dict) -> list[str]:
    kws = cfg["keywords"]
    if isinstance(kws, str):
        return [k.strip() for k in kws.split(",") if k.strip()]
    if isinstance(kws, list):
        return kws
    return []


@app.route("/api/keywords", methods=["GET"])
@login_required
def api_get_keywords():
    cfg = db.get_user_config(session["user_id"])
    kws = _parse_keywords(cfg)
    mode = cfg.get("keyword_mode", "exact")
    return jsonify({"keywords": kws, "mode": mode})


def _sync_monitor_detector(uid: int, keywords: list[str], mode: str):
    """Push updated keywords/mode to the running monitor for this user."""
    with monitor_lock:
        m = monitors.get(uid)
    if m and m.running:
        m.detector.set_keywords(keywords)
        m.detector.keyword_mode = mode
        logger.info(f"已同步关键词到运行中的监控: {len(keywords)} 个关键词, mode={mode}")


@app.route("/api/keywords", methods=["POST"])
@login_required
def api_add_keyword():
    data = request.get_json()
    kw = data.get("keyword", "").strip()
    if not kw:
        return jsonify({"ok": False, "error": "关键词不能为空"})
    cfg = db.get_user_config(session["user_id"])
    kws = _parse_keywords(cfg)
    if kw in kws:
        return jsonify({"ok": False, "error": "关键词已存在"})
    kws.append(kw)
    cfg["keywords"] = ",".join(kws)
    db.save_user_config(session["user_id"], cfg)
    _sync_monitor_detector(
        session["user_id"], kws, cfg.get("keyword_mode", "exact"))
    return jsonify({"ok": True, "keyword": kw})


@app.route("/api/keywords/<kw>", methods=["DELETE"])
@login_required
def api_delete_keyword(kw):
    cfg = db.get_user_config(session["user_id"])
    kws = _parse_keywords(cfg)
    if kw in kws:
        kws.remove(kw)
    cfg["keywords"] = ",".join(kws)
    db.save_user_config(session["user_id"], cfg)
    _sync_monitor_detector(
        session["user_id"], kws, cfg.get("keyword_mode", "exact"))
    return jsonify({"ok": True})


@app.route("/api/keywords/reset", methods=["POST"])
@login_required
def api_reset_keywords():
    cfg = db.get_user_config(session["user_id"])
    cfg["keywords"] = DEFAULT_KEYWORDS_STR
    cfg["keyword_mode"] = "exact"
    db.save_user_config(session["user_id"], cfg)
    kws = _parse_keywords(cfg)
    _sync_monitor_detector(session["user_id"], kws, "exact")
    return jsonify({"ok": True, "keywords": DEFAULT_KEYWORDS_STR, "mode": "exact"})


# ---------------------------------------------------------------------------
# Messages API
# ---------------------------------------------------------------------------

@app.route("/api/messages", methods=["GET"])
@login_required
def api_get_messages():
    uid = session["user_id"]
    keyword = request.args.get("keyword", "")
    sender = request.args.get("sender", "")
    limit = int(request.args.get("limit", 200))
    offset = int(request.args.get("offset", 0))
    messages = db.query_messages(
        user_id=uid,
        keyword=keyword if keyword else None,
        sender=sender if sender else None,
        limit=limit, offset=offset,
    )
    senders = db.get_unique_senders(user_id=uid)
    all_keywords = db.get_unique_keywords(user_id=uid)
    return jsonify({
        "messages": messages,
        "senders": senders,
        "all_keywords": all_keywords,
    })


@app.route("/api/messages/<int:msg_id>", methods=["GET"])
@login_required
def api_get_message(msg_id):
    msgs = db.query_messages(user_id=session["user_id"], limit=500)
    for m in msgs:
        if m["id"] == msg_id:
            return jsonify({"ok": True, "message": m})
    return jsonify({"ok": False, "error": "消息不存在"})


@app.route("/api/messages/<int:msg_id>", methods=["DELETE"])
@login_required
def api_delete_message(msg_id):
    db.delete_message(msg_id)
    return jsonify({"ok": True})


@app.route("/api/messages/clear", methods=["POST"])
@login_required
def api_clear_messages():
    db.clear_all(user_id=session["user_id"])
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Monitor API
# ---------------------------------------------------------------------------

class _ConfigProxy:
    """Adapter so Monitor.config behaves like the real Config object."""
    def __init__(self, data: dict):
        self._data = data

    def get(self, key, default=None):
        return self._data.get(key, default)

    def get_region_dict(self):
        r = self._data.get("region", {})
        return {
            "left": int(r.get("left", 0)),
            "top": int(r.get("top", 0)),
            "width": int(r.get("width", 800)),
            "height": int(r.get("height", 600)),
        }


def _get_or_create_monitor(user_id: int) -> Monitor:
    with monitor_lock:
        if user_id not in monitors:
            cfg = db.get_user_config(user_id)
            kws = _parse_keywords(cfg)
            detector = Detector(kws, cfg.get("keyword_mode", "exact"))
            monitors[user_id] = Monitor(None, ocr, detector, db)
        return monitors[user_id]


@app.route("/api/monitor/start", methods=["POST"])
@login_required
def api_monitor_start():
    uid = session["user_id"]
    cfg = db.get_user_config(uid)
    kws = _parse_keywords(cfg)
    if not kws:
        return jsonify({"ok": False, "error": "请先设置关键词"})

    m = _get_or_create_monitor(uid)
    m.user_id = uid
    m.detector.set_keywords(kws)
    m.detector.keyword_mode = cfg.get("keyword_mode", "exact")
    m.config = _ConfigProxy(cfg)
    m.start()
    return jsonify({"ok": True})


@app.route("/api/monitor/stop", methods=["POST"])
@login_required
def api_monitor_stop():
    uid = session["user_id"]
    with monitor_lock:
        if uid in monitors:
            monitors[uid].stop()
    return jsonify({"ok": True})


@app.route("/api/monitor/status", methods=["GET"])
@login_required
def api_monitor_status():
    uid = session["user_id"]
    with monitor_lock:
        if uid in monitors:
            st = monitors[uid].get_status()
            st["running"] = monitors[uid].running
            return jsonify(st)
    return jsonify({
        "running": False, "captures": 0,
        "detections": 0, "last_capture": None,
    })


# ---------------------------------------------------------------------------
# Region API
# ---------------------------------------------------------------------------

def _parse_region(data: dict) -> dict:
    return {
        "left": int(data.get("left", 0)),
        "top": int(data.get("top", 0)),
        "width": int(data.get("width", 600)),
        "height": int(data.get("height", 400)),
    }


@app.route("/api/region/preview", methods=["POST"])
@login_required
def api_region_preview():
    import mss
    from PIL import Image

    data = request.get_json()
    region = _parse_region(data)
    try:
        with mss.MSS() as sct:
            img = sct.grab(region)
            pil_img = Image.frombytes("RGB", img.size, img.rgb)
            buf = io.BytesIO()
            pil_img.save(buf, format="JPEG", quality=90)
            b64 = base64.b64encode(buf.getvalue()).decode()
            return jsonify({
                "ok": True,
                "image": f"data:image/jpeg;base64,{b64}",
                "width": pil_img.width,
                "height": pil_img.height,
            })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/region/set", methods=["POST"])
@login_required
def api_region_set():
    data = request.get_json()
    region = _parse_region(data)
    cfg = db.get_user_config(session["user_id"])
    cfg["region"] = region
    db.save_user_config(session["user_id"], cfg)
    return jsonify({"ok": True, "region": region})


# ---------------------------------------------------------------------------
# Export API
# ---------------------------------------------------------------------------

@app.route("/api/export", methods=["POST"])
@login_required
def api_export():
    export_dir = Path(os.getenv("APPDATA")) / "QQMonitor" / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    path = export_dir / f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    db.export_csv(str(path), user_id=session["user_id"])
    return jsonify({"ok": True, "path": str(path)})


# ---------------------------------------------------------------------------
# User info
# ---------------------------------------------------------------------------

@app.route("/api/user", methods=["GET"])
@login_required
def api_user():
    return jsonify({"username": session.get("username")})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("Web 应用启动中...")
    print("\n  QQ群消息监控 — Web版")
    print("  浏览器打开: http://127.0.0.1:5000\n")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
