import os
import sys
import time
import json
import queue
import threading
import logging
from pathlib import Path
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, request, jsonify, session, redirect, url_for

# ---- Setup ----

def set_dpi_aware():
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

set_dpi_aware()

log_dir = Path(os.getenv('APPDATA')) / 'QQMonitor' / 'logs'
log_dir.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(log_dir / 'webapp.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.urandom(24).hex()

from database import Database
from ocr_engine import OCREngine
from detector import Detector
from monitor import Monitor

db = Database()
ocr = OCREngine()

# per-user monitor instances
monitors = {}
monitor_lock = threading.Lock()

# ---- Auth helpers ----

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated

# ---- Page routes ----

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/')
@login_required
def index():
    return render_template('index.html')

# ---- Auth API ----

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')
    if not username or not password:
        return jsonify({'ok': False, 'error': '用户名和密码不能为空'})
    user = db.verify_user(username, password)
    if user:
        session['user_id'] = user['id']
        session['username'] = user['username']
        return jsonify({'ok': True, 'username': user['username']})
    return jsonify({'ok': False, 'error': '用户名或密码错误'})

@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')
    if len(username) < 2:
        return jsonify({'ok': False, 'error': '用户名至少2个字符'})
    if len(password) < 3:
        return jsonify({'ok': False, 'error': '密码至少3个字符'})
    user_id = db.create_user(username, password)
    if user_id:
        session['user_id'] = user_id
        session['username'] = username
        return jsonify({'ok': True, 'username': username})
    return jsonify({'ok': False, 'error': '用户名已存在'})

@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'ok': True})

# ---- Config API ----

@app.route('/api/config', methods=['GET'])
@login_required
def api_get_config():
    uid = session['user_id']
    cfg = db.get_user_config(uid)
    cfg['has_region'] = any([
        cfg['region']['left'] != 0,
        cfg['region']['top'] != 0,
        cfg['region']['width'] != 800,
        cfg['region']['height'] != 600,
    ])
    return jsonify(cfg)

@app.route('/api/config', methods=['POST'])
@login_required
def api_save_config():
    data = request.get_json()
    db.save_user_config(session['user_id'], data)
    return jsonify({'ok': True})

# ---- Keywords API ----

@app.route('/api/keywords', methods=['GET'])
@login_required
def api_get_keywords():
    cfg = db.get_user_config(session['user_id'])
    kws = cfg['keywords']
    if isinstance(kws, str):
        kws = [k.strip() for k in kws.split(',') if k.strip()]
    elif not isinstance(kws, list):
        kws = []
    mode = cfg.get('keyword_mode', 'exact')
    return jsonify({'keywords': kws, 'mode': mode})

@app.route('/api/keywords', methods=['POST'])
@login_required
def api_add_keyword():
    data = request.get_json()
    kw = data.get('keyword', '').strip()
    if not kw:
        return jsonify({'ok': False, 'error': '关键词不能为空'})
    cfg = db.get_user_config(session['user_id'])
    kws = cfg['keywords']
    if isinstance(kws, str):
        kws = [k.strip() for k in kws.split(',') if k.strip()]
    elif not isinstance(kws, list):
        kws = []
    if kw in kws:
        return jsonify({'ok': False, 'error': '关键词已存在'})
    kws.append(kw)
    cfg['keywords'] = ','.join(kws)
    db.save_user_config(session['user_id'], cfg)
    return jsonify({'ok': True, 'keyword': kw})

@app.route('/api/keywords/<kw>', methods=['DELETE'])
@login_required
def api_delete_keyword(kw):
    cfg = db.get_user_config(session['user_id'])
    kws = cfg['keywords']
    if isinstance(kws, str):
        kws = [k.strip() for k in kws.split(',') if k.strip()]
    if kw in kws:
        kws.remove(kw)
    cfg['keywords'] = ','.join(kws)
    db.save_user_config(session['user_id'], cfg)
    return jsonify({'ok': True})

@app.route('/api/keywords/reset', methods=['POST'])
@login_required
def api_reset_keywords():
    default = '考试,考核,测验,作业,截止日期,提交,考试时间,试卷,成绩,期末,期中,补考,答辩,实验报告,签到,点名'
    cfg = db.get_user_config(session['user_id'])
    cfg['keywords'] = default
    cfg['keyword_mode'] = 'exact'
    db.save_user_config(session['user_id'], cfg)
    return jsonify({'ok': True, 'keywords': default, 'mode': 'exact'})

# ---- Messages API ----

@app.route('/api/messages', methods=['GET'])
@login_required
def api_get_messages():
    uid = session['user_id']
    keyword = request.args.get('keyword', '')
    sender = request.args.get('sender', '')
    limit = int(request.args.get('limit', 200))
    offset = int(request.args.get('offset', 0))
    messages = db.query_messages(
        user_id=uid, keyword=keyword if keyword else None,
        sender=sender if sender else None,
        limit=limit, offset=offset,
    )
    senders = db.get_unique_senders(user_id=uid)
    all_keywords = db.get_unique_keywords(user_id=uid)
    return jsonify({
        'messages': messages,
        'senders': senders,
        'all_keywords': all_keywords,
    })

@app.route('/api/messages/<int:msg_id>', methods=['GET'])
@login_required
def api_get_message(msg_id):
    msgs = db.query_messages(user_id=session['user_id'], limit=500)
    for m in msgs:
        if m['id'] == msg_id:
            return jsonify({'ok': True, 'message': m})
    return jsonify({'ok': False, 'error': '消息不存在'})

@app.route('/api/messages/<int:msg_id>', methods=['DELETE'])
@login_required
def api_delete_message(msg_id):
    db.delete_message(msg_id)
    return jsonify({'ok': True})

@app.route('/api/messages/clear', methods=['POST'])
@login_required
def api_clear_messages():
    db.clear_all(user_id=session['user_id'])
    return jsonify({'ok': True})

# ---- Monitor API ----

def _get_or_create_monitor(user_id):
    with monitor_lock:
        if user_id not in monitors:
            cfg = db.get_user_config(user_id)
            kws = cfg['keywords']
            if isinstance(kws, str):
                kws = [k.strip() for k in kws.split(',') if k.strip()]
            detector = Detector(kws, cfg.get('keyword_mode', 'exact'))
            monitors[user_id] = Monitor(None, ocr, detector, db)
        return monitors[user_id]

@app.route('/api/monitor/start', methods=['POST'])
@login_required
def api_monitor_start():
    uid = session['user_id']
    cfg = db.get_user_config(uid)
    kws = cfg['keywords']
    if isinstance(kws, str):
        kws = [k.strip() for k in kws.split(',') if k.strip()]
    if not kws:
        return jsonify({'ok': False, 'error': '请先设置关键词'})

    m = _get_or_create_monitor(uid)
    m.user_id = uid
    m.detector.set_keywords(kws)
    m.detector.keyword_mode = cfg.get('keyword_mode', 'exact')
    m.config = type('obj', (object,), {
        'get': lambda k, d=None: cfg.get(k, d),
        'get_region_dict': lambda: _fix_region(cfg.get('region', {})),
        'set': lambda k, v: None,
    })()
    m.start()
    return jsonify({'ok': True})

def _fix_region(r):
    return {
        'left': int(r.get('left', 0)),
        'top': int(r.get('top', 0)),
        'width': int(r.get('width', 800)),
        'height': int(r.get('height', 600)),
    }

@app.route('/api/monitor/stop', methods=['POST'])
@login_required
def api_monitor_stop():
    uid = session['user_id']
    with monitor_lock:
        if uid in monitors:
            monitors[uid].stop()
    return jsonify({'ok': True})

@app.route('/api/monitor/status', methods=['GET'])
@login_required
def api_monitor_status():
    uid = session['user_id']
    with monitor_lock:
        if uid in monitors:
            st = monitors[uid].get_status()
            st['running'] = monitors[uid].running
            return jsonify(st)
    return jsonify({'running': False, 'captures': 0, 'detections': 0, 'last_capture': None})

# ---- Region select API ----

@app.route('/api/region/select', methods=['POST'])
@login_required
def api_region_select():
    import subprocess
    script = os.path.join(os.path.dirname(__file__), 'select_region.py')
    try:
        result = subprocess.run(
            [sys.executable, script],
            capture_output=True, text=True, timeout=120,
            cwd=os.path.dirname(__file__),
        )
        output = result.stdout.strip()
        if output and output != 'null':
            region = json.loads(output)
            cfg = db.get_user_config(session['user_id'])
            cfg['region'] = region
            db.save_user_config(session['user_id'], cfg)
            return jsonify({'ok': True, 'region': region})
        return jsonify({'ok': False, 'error': '未选择区域'})
    except subprocess.TimeoutExpired:
        return jsonify({'ok': False, 'error': '操作超时'})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@app.route('/api/region/set', methods=['POST'])
@login_required
def api_region_set():
    data = request.get_json()
    region = {
        'left': int(data.get('left', 0)),
        'top': int(data.get('top', 0)),
        'width': int(data.get('width', 800)),
        'height': int(data.get('height', 600)),
    }
    cfg = db.get_user_config(session['user_id'])
    cfg['region'] = region
    db.save_user_config(session['user_id'], cfg)
    return jsonify({'ok': True})

# ---- Export API ----

@app.route('/api/export', methods=['POST'])
@login_required
def api_export():
    export_dir = Path(os.getenv('APPDATA')) / 'QQMonitor' / 'exports'
    export_dir.mkdir(parents=True, exist_ok=True)
    path = export_dir / f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    db.export_csv(str(path), user_id=session['user_id'])
    return jsonify({'ok': True, 'path': str(path)})

# ---- User info ----

@app.route('/api/user', methods=['GET'])
@login_required
def api_user():
    return jsonify({'username': session.get('username')})

# ---- Run ----

if __name__ == '__main__':
    logger.info("Web 应用启动中...")
    print("\n  QQ群消息监控 — Web版")
    print("  浏览器打开: http://127.0.0.1:5000\n")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
