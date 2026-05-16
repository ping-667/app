// ---- Globals ----
let currentTab = 'history';
let regionStart = null;
let regionEnd = null;

// ---- Init ----
document.addEventListener('DOMContentLoaded', () => {
    fetch('/api/user').then(r => r.json()).then(d => {
        document.getElementById('user-display').textContent = d.username || '';
    });
    loadConfig();
    loadMessages();
    pollMonitorStatus();
    setInterval(pollMonitorStatus, 3000);
    setInterval(loadMessages, 10000);  // auto-refresh every 10s
});

// ---- Tabs ----
function switchMainTab(tab, el) {
    currentTab = tab;
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    el.classList.add('active');
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    document.getElementById('tab-' + tab).classList.add('active');
    if (tab === 'history') loadMessages();
    if (tab === 'keywords') loadKeywords();
    if (tab === 'settings') loadConfig();
}

// ---- Auth ----
async function doLogout() {
    await fetch('/api/logout', { method: 'POST' });
    window.location.href = '/login';
}

// ---- Config ----
async function loadConfig() {
    const r = await fetch('/api/config');
    const c = await r.json();
    document.getElementById('interval-input').value = c.interval_seconds || 5;
    document.getElementById('group-input').value = c.group_name || '默认';
    document.getElementById('notify-check').checked = c.notification_enabled !== false;
    document.getElementById('screenshot-check').checked = c.save_screenshots === true;
    const ri = document.getElementById('region-info');
    ri.textContent = `左:${c.region.left} 上:${c.region.top} 宽:${c.region.width} 高:${c.region.height}`;
}

async function saveSettings() {
    const cfg = {
        interval_seconds: parseInt(document.getElementById('interval-input').value) || 5,
        group_name: document.getElementById('group-input').value || '默认',
        notification_enabled: document.getElementById('notify-check').checked,
        save_screenshots: document.getElementById('screenshot-check').checked,
    };
    await fetch('/api/config', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(cfg) });
}

// ---- Messages ----
async function loadMessages() {
    const search = document.getElementById('search-input')?.value || '';
    const sender = document.getElementById('sender-filter')?.value || '';
    const keyword = document.getElementById('keyword-filter')?.value || '';
    const r = await fetch(`/api/messages?keyword=${encodeURIComponent(keyword)}&sender=${encodeURIComponent(sender)}&limit=300`);
    const d = await r.json();

    // Update filter dropdowns
    const sf = document.getElementById('sender-filter');
    sf.innerHTML = '<option value="">全部发送者</option>' + d.senders.map(s => `<option>${s}</option>`).join('');
    const kf = document.getElementById('keyword-filter');
    kf.innerHTML = '<option value="">全部关键词</option>' + d.all_keywords.map(k => `<option>${k}</option>`).join('');

    // Apply search filter client-side
    let msgs = d.messages;
    if (search) {
        const q = search.toLowerCase();
        msgs = msgs.filter(m => m.content.toLowerCase().includes(q));
    }

    const tbody = document.getElementById('msg-table');
    const noMsgs = document.getElementById('no-messages');

    if (msgs.length === 0) {
        tbody.innerHTML = '';
        noMsgs.style.display = 'block';
    } else {
        noMsgs.style.display = 'none';
        tbody.innerHTML = msgs.map(m => `
            <tr>
                <td>${(m.detected_at || '').substring(0, 19)}</td>
                <td><strong>${escHtml(m.sender)}</strong></td>
                <td title="${escAttr(m.content)}">${escHtml(m.content.length > 60 ? m.content.substring(0, 60) + '...' : m.content)}</td>
                <td style="color:#e53935">${escHtml(m.matched_keywords)}</td>
                <td>
                    <a href="javascript:showDetail(${m.id})" style="color:#1a73e8;font-size:12px;cursor:pointer">详情</a>
                    <a href="javascript:delMsg(${m.id})" style="color:#999;font-size:12px;cursor:pointer;margin-left:8px">删</a>
                </td>
            </tr>
        `).join('');
    }
}

async function showDetail(id) {
    const r = await fetch(`/api/messages/${id}`);
    const d = await r.json();
    if (!d.ok) return;
    const m = d.message;
    document.getElementById('detail-body').innerHTML = `
        <div class="detail-field"><span class="detail-label">发送者：</span>${escHtml(m.sender)}</div>
        <div class="detail-field"><span class="detail-label">时间：</span>${m.detected_at}</div>
        <div class="detail-field"><span class="detail-label">关键词：</span><span style="color:#e53935">${escHtml(m.matched_keywords)}</span></div>
        <div class="detail-field"><span class="detail-label">群组：</span>${escHtml(m.group_name || '默认')}</div>
        <div class="detail-label">消息内容：</div>
        <div class="detail-content">${escHtml(m.content)}</div>
    `;
    document.getElementById('detail-modal').classList.add('show');
}

function closeDetail() {
    document.getElementById('detail-modal').classList.remove('show');
}

async function delMsg(id) {
    if (!confirm('确定删除这条记录？')) return;
    await fetch(`/api/messages/${id}`, { method: 'DELETE' });
    loadMessages();
}

async function exportCSV() {
    const r = await fetch('/api/export', { method: 'POST' });
    const d = await r.json();
    if (d.ok) alert('已导出到: ' + d.path);
}

// ---- Keywords ----
async function loadKeywords() {
    const r = await fetch('/api/keywords');
    const d = await r.json();
    document.getElementById('kw-mode-select').value = d.mode || 'exact';
    const list = document.getElementById('kw-list');
    if (d.keywords.length === 0) {
        list.innerHTML = '<span style="color:#999;font-size:13px">暂无关键词，请添加</span>';
    } else {
        list.innerHTML = d.keywords.map(k => `
            <span class="kw-tag">${escHtml(k)}<span class="kw-del" onclick="delKeyword('${escAttr(k)}')">&times;</span></span>
        `).join('');
    }
}

async function addKeyword() {
    const inp = document.getElementById('kw-input');
    const kw = inp.value.trim();
    if (!kw) return;
    const r = await fetch('/api/keywords', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({keyword: kw}) });
    const d = await r.json();
    if (!d.ok) { alert(d.error); return; }
    inp.value = '';
    loadKeywords();
}

async function batchAdd() {
    const inp = document.getElementById('kw-batch');
    const text = inp.value.trim();
    if (!text) return;
    const kws = text.split(/[,，\s]+/).filter(k => k);
    for (const kw of kws) {
        await fetch('/api/keywords', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({keyword: kw}) });
    }
    inp.value = '';
    loadKeywords();
}

async function delKeyword(kw) {
    await fetch('/api/keywords/' + encodeURIComponent(kw), { method: 'DELETE' });
    loadKeywords();
}

async function changeMode() {
    const mode = document.getElementById('kw-mode-select').value;
    await fetch('/api/config', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({keyword_mode: mode, keywords: ''}) });
    // Preserve keywords - get current, update mode
    const r = await fetch('/api/keywords');
    const d = await r.json();
    await fetch('/api/config', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({keyword_mode: mode, keywords: (d.keywords||[]).join(',')}) });
}

async function resetKeywords() {
    if (!confirm('确定恢复默认关键词？')) return;
    await fetch('/api/keywords/reset', { method: 'POST' });
    loadKeywords();
}

// ---- Monitor ----
async function startMonitor() {
    const r = await fetch('/api/monitor/start', { method: 'POST' });
    const d = await r.json();
    if (!d.ok) { alert(d.error); return; }
    updateMonitorUI(true);
}

async function stopMonitor() {
    await fetch('/api/monitor/stop', { method: 'POST' });
    updateMonitorUI(false);
}

function updateMonitorUI(running) {
    const status = document.getElementById('monitor-status');
    const btnStart = document.getElementById('btn-start');
    const btnStop = document.getElementById('btn-stop');
    if (running) {
        status.textContent = '● 运行中';
        status.className = 'monitor-status running';
        btnStart.disabled = true;
        btnStop.disabled = false;
    } else {
        status.textContent = '○ 已停止';
        status.className = 'monitor-status stopped';
        btnStart.disabled = false;
        btnStop.disabled = true;
    }
}

async function pollMonitorStatus() {
    try {
        const r = await fetch('/api/monitor/status');
        const d = await r.json();
        updateMonitorUI(d.running);
    } catch (e) { /* ignore */ }
}

// ---- Region Select ----
let regionScale = 1;
let regionOrigW = 1920;
let regionOrigH = 1080;
let regionDragStart = null;
let regionBoxEl = null;
let regionImgEl = null;

async function selectRegion() {
    const overlay = document.getElementById('region-overlay');
    const img = document.getElementById('region-img');
    const box = document.getElementById('region-box');
    const ri = document.getElementById('region-info');
    regionBoxEl = box;
    regionImgEl = img;

    ri.textContent = '正在截图...';
    overlay.style.display = 'flex';
    img.src = '';
    box.style.display = 'none';
    regionDragStart = null;

    try {
        const r = await fetch('/api/screenshot');
        const d = await r.json();
        if (!d.ok) { alert('截图失败'); overlay.style.display = 'none'; return; }
        img.src = d.image;
        regionScale = d.scale;
        regionOrigW = d.orig_width;
        regionOrigH = d.orig_height;
        ri.textContent = `左:0 上:0 宽:800 高:600`;
    } catch (e) {
        alert('截图出错: ' + e.message);
        overlay.style.display = 'none';
    }
}

function confirmRegion() {
    const box = regionBoxEl;
    const overlay = document.getElementById('region-overlay');
    if (!box || box.style.display === 'none') {
        alert('请先在截图上拖拽框选区域');
        return;
    }
    const left = parseInt(box.style.left);
    const top = parseInt(box.style.top);
    const w = parseInt(box.style.width);
    const h = parseInt(box.style.height);
    if (w < 20 || h < 20) {
        alert('框选区域太小，请重新选择');
        return;
    }
    fetch('/api/region/set', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({left, top, width: w, height: h, scale: regionScale}),
    }).then(r => r.json()).then(d => {
        if (d.ok) {
            document.getElementById('region-info').textContent =
                `左:${d.region.left} 上:${d.region.top} 宽:${d.region.width} 高:${d.region.height}`;
        }
    });
    overlay.style.display = 'none';
}

function cancelRegion() {
    document.getElementById('region-overlay').style.display = 'none';
    document.getElementById('region-info').textContent = '已取消';
}

// Mouse events on the screenshot
document.addEventListener('DOMContentLoaded', function() {
    const overlay = document.getElementById('region-overlay');
    const img = document.getElementById('region-img');
    const box = document.getElementById('region-box');
    const posLabel = document.getElementById('region-pos');

    img.addEventListener('mousedown', function(e) {
        e.preventDefault();
        const rect = img.getBoundingClientRect();
        regionDragStart = { x: e.clientX - rect.left, y: e.clientY - rect.top };
        box.style.left = regionDragStart.x + 'px';
        box.style.top = regionDragStart.y + 'px';
        box.style.width = '0px';
        box.style.height = '0px';
        box.style.display = 'block';
    });

    img.addEventListener('mousemove', function(e) {
        if (!regionDragStart) return;
        e.preventDefault();
        const rect = img.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        const left = Math.min(regionDragStart.x, x);
        const top = Math.min(regionDragStart.y, y);
        const w = Math.abs(x - regionDragStart.x);
        const h = Math.abs(y - regionDragStart.y);
        box.style.left = left + 'px';
        box.style.top = top + 'px';
        box.style.width = w + 'px';
        box.style.height = h + 'px';
        posLabel.textContent = `X:${Math.round(left/regionScale)} Y:${Math.round(top/regionScale)}  宽:${Math.round(w/regionScale)} 高:${Math.round(h/regionScale)}`;
    });

    img.addEventListener('mouseup', function(e) {
        // Keep regionDragStart so confirmRegion can validate
    });
});

// ---- Utils ----
function escHtml(s) {
    if (!s) return '';
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}
function escAttr(s) {
    return (s || '').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// Close modal on backdrop click
document.addEventListener('click', function(e) {
    if (e.target.id === 'detail-modal') closeDetail();
});
