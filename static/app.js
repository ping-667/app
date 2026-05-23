// ---- Globals ----
let currentTab = 'history';

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
    if (tab === 'stats') loadStats();
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
    document.getElementById('ws-url-input').value = c.ws_url || 'ws://127.0.0.1:3001';
}

async function saveSettings() {
    const cfg = {
        interval_seconds: parseInt(document.getElementById('interval-input').value) || 5,
        group_name: document.getElementById('group-input').value || '默认',
        notification_enabled: document.getElementById('notify-check').checked,
        ws_url: document.getElementById('ws-url-input').value || 'ws://127.0.0.1:3001',
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
                <td class="keyword-col">${escHtml(m.matched_keywords)}</td>
                <td>
                    <a href="javascript:showDetail(${m.id})" class="text-cyan" style="font-size:12px;cursor:pointer">详情</a>
                    <a href="javascript:delMsg(${m.id})" style="color:var(--text-dim);font-size:12px;cursor:pointer;margin-left:10px">删</a>
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
        <div class="detail-field"><span class="detail-label">发送者</span><br>${escHtml(m.sender)}</div>
        <div class="detail-field"><span class="detail-label">时间</span><br>${m.detected_at}</div>
        <div class="detail-field"><span class="detail-label">关键词</span><br><span class="text-red">${escHtml(m.matched_keywords)}</span></div>
        <div class="detail-field"><span class="detail-label">群组</span><br>${escHtml(m.group_name || '默认')}</div>
        <div class="detail-label">消息内容</div>
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

// ---- Statistics ----
let chartInstances = {};

async function loadStats() {
    const r = await fetch('/api/statistics');
    const d = await r.json();
    document.getElementById('stat-total').textContent = d.total || 0;

    // Destroy previous charts
    Object.values(chartInstances).forEach(c => c.destroy());
    chartInstances = {};

    // Keyword bar chart
    const kwLabels = (d.keyword_counts || []).map(k => k[0]);
    const kwValues = (d.keyword_counts || []).map(k => k[1]);
    if (kwLabels.length > 0) {
        const ctx1 = document.getElementById('chart-keywords').getContext('2d');
        chartInstances.keywords = new Chart(ctx1, {
            type: 'bar',
            data: {
                labels: kwLabels,
                datasets: [{
                    label: '命中次数',
                    data: kwValues,
                    backgroundColor: kwLabels.map((_, i) =>
                        `hsla(${190 + i * 15}, 90%, 50%, 0.7)`),
                    borderColor: kwLabels.map((_, i) =>
                        `hsl(${190 + i * 15}, 90%, 50%)`),
                    borderWidth: 1,
                    borderRadius: 4,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                },
                scales: {
                    x: {
                        ticks: { color: '#5a6478', font: { size: 11 } },
                        grid: { color: 'rgba(255,255,255,0.04)' },
                    },
                    y: {
                        beginAtZero: true,
                        ticks: { color: '#5a6478', font: { size: 11 }, stepSize: 1 },
                        grid: { color: 'rgba(255,255,255,0.04)' },
                    },
                },
            },
        });
    }

    // Sender doughnut chart
    const sLabels = (d.top_senders || []).map(s => s.sender);
    const sValues = (d.top_senders || []).map(s => s.cnt);
    if (sLabels.length > 0) {
        const ctx2 = document.getElementById('chart-senders').getContext('2d');
        chartInstances.senders = new Chart(ctx2, {
            type: 'doughnut',
            data: {
                labels: sLabels,
                datasets: [{
                    data: sValues,
                    backgroundColor: [
                        'rgba(0,200,232,0.8)', 'rgba(240,168,40,0.8)',
                        'rgba(46,204,113,0.8)', 'rgba(240,62,77,0.8)',
                        'rgba(155,89,182,0.8)', 'rgba(52,152,219,0.8)',
                        'rgba(230,126,34,0.8)', 'rgba(26,188,156,0.8)',
                        'rgba(149,165,166,0.8)', 'rgba(255,107,129,0.8)',
                    ],
                    borderColor: '#161d2a',
                    borderWidth: 2,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: { color: '#94a3b8', font: { size: 11 }, padding: 14, usePointStyle: true },
                    },
                },
            },
        });
    }
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
    await fetch('/api/config', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({keyword_mode: mode}),
    });
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
