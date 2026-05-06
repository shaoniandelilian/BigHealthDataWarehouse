// ===== Product Research App v3 - Streaming Frontend =====

let currentConvoId = null;
let pollTimer = null;
let liveRecordCount = 0;  // 已渲染的记录数，用于增量拉取

document.addEventListener('DOMContentLoaded', () => { loadHistory(); });

// ---- 侧栏历史 ----
async function loadHistory() {
    try {
        const res = await fetch('/api/conversations');
        const convos = await res.json();
        renderHistory(convos);
    } catch (e) { console.error('加载历史失败:', e); }
}

function renderHistory(convos) {
    const el = document.getElementById('chatList');
    if (!convos.length) { el.innerHTML = '<div class="sb-empty">暂无历史记录</div>'; return; }
    convos.sort((a, b) => {
        const timeA = new Date(a.created.replace(/-/g, '/') + (a.created.length <= 16 ? ':00' : ''));
        const timeB = new Date(b.created.replace(/-/g, '/') + (b.created.length <= 16 ? ':00' : ''));
        return timeB - timeA;
    });
    el.innerHTML = convos.map(c => {
        const dotClass = c.status === 'done' ? 'done' : c.status === 'running' ? 'running' : (c.status === 'error' ? 'error' : '');
        return `<div class="sb-item ${c.id === currentConvoId ? 'active' : ''}" onclick="viewResult('${c.id}')">
            <div class="sb-text">
                <div class="sb-title">${escapeHtml(c.title)}</div>
                <div class="sb-time">${c.updated || c.created}</div>
            </div>
            ${c.status !== 'pending' && c.status !== 'done' ? `<span class="sb-status-dot ${dotClass}"></span>` : ''}
        </div>`;
    }).join('');
}

// ---- 提交主题 ----
async function submitTopic() {
    const input = document.getElementById('topicInput');
    const btn = document.getElementById('submitBtn');
    const text = input.value.trim();
    if (!text) { input.focus(); return; }

    showResultView(text);
    btn.disabled = true;

    try {
        const res = await fetch('/api/submit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ topic: text }),
        });
        const data = await res.json();
        if (data.error) { showError(data.error); return; }

        currentConvoId = data.conversation_id;
        document.getElementById('resultTitle').textContent = text;
        loadHistory();
        startPolling(data.conversation_id);
    } catch (e) {
        showError('网络错误: ' + e.message);
        btn.disabled = false;
    }
}

// ---- 状态轮询（合并状态 + 增量记录） ----
function startPolling(cid) {
    if (pollTimer) clearInterval(pollTimer);
    liveRecordCount = 0;
    // 立即显示表格区域（空表头）
    showLiveTable();
    pollTimer = setInterval(() => pollLive(cid), 3000);
    pollLive(cid);
}

async function pollLive(cid) {
    try {
        // 并行拉取状态和新记录
        const [statusRes, recordsRes] = await Promise.all([
            fetch(`/api/conversation/${cid}/status`),
            fetch(`/api/conversation/${cid}/records?offset=${liveRecordCount}`)
        ]);
        const s = await statusRes.json();
        const r = await recordsRes.json();

        // 追加新行
        if (r.records && r.records.length > 0) {
            appendRows(r.records);
            liveRecordCount = r.total;
        }
        updateLiveCount(r.total || liveRecordCount);

        // 状态处理
        if (s.status === 'pending') {
            updateStatusText('已提交，等待调研启动...');
        } else if (s.status === 'running') {
            updateStatusText(`正在采集中... 已获取 ${r.total || 0} 条产品`);
        } else if (s.status === 'done') {
            clearInterval(pollTimer);
            pollTimer = null;
            showDone(s);
            loadHistory();
        } else if (s.status === 'error') {
            clearInterval(pollTimer);
            pollTimer = null;
            showError(s.error || '处理出错，请重试');
        }
    } catch (e) { console.error('轮询错误:', e); }
}

// ---- 实时表格渲染 ----
const TABLE_COLS = [
    { key: 'product_name', label: '产品名称' },
    { key: 'brand', label: '品牌' },
    { key: 'source_platform', label: '平台' },
    { key: 'price', label: '价格' },
    { key: 'dosage_form', label: '剂型' },
    { key: 'pack_size', label: '规格' },
    { key: 'core_ingredients', label: '核心原料' },
    { key: 'core_selling_points', label: '核心卖点' },
    { key: 'target_population', label: '适用人群' },
];

function showLiveTable() {
    document.getElementById('reportResult').classList.remove('hidden');
    document.getElementById('dlJsonBtn').href = `/api/conversation/${currentConvoId}/json`;
    document.getElementById('dlExcelBtn').href = `/api/conversation/${currentConvoId}/excel`;
    document.getElementById('downloadArea').classList.remove('hidden');
    renderTableHead();
    document.getElementById('dataTbody').innerHTML = '';
}

function renderTableHead() {
    document.getElementById('dataThead').innerHTML =
        '<tr>' + TABLE_COLS.map(c => `<th>${c.label}</th>`).join('') + '</tr>';
}

function appendRows(records) {
    const tbody = document.getElementById('dataTbody');
    const html = records.map(r =>
        '<tr class="new-row">' + TABLE_COLS.map(c => {
            const val = String(r[c.key] || '');
            if (c.key === 'source_platform' && r.product_url) {
                return `<td><a href="${escapeHtml(r.product_url)}" target="_blank" rel="noopener">${escapeHtml(val)}</a></td>`;
            }
            if (val.length > 50) {
                return `<td class="td-ellipsis" onclick="this.classList.toggle('expanded')" title="${escapeHtml(val)}">${escapeHtml(val)}</td>`;
            }
            return `<td>${escapeHtml(val)}</td>`;
        }).join('') + '</tr>'
    ).join('');
    tbody.insertAdjacentHTML('beforeend', html);
    // 滚动到底部
    const wrapper = document.getElementById('tableWrapper');
    wrapper.scrollTop = wrapper.scrollHeight;
}

function updateLiveCount(n) {
    document.getElementById('tableCount').textContent = `已采集 ${n} 条`;
}

// ---- 完成状态 ----
function showDone(statusData) {
    document.getElementById('statusCard').classList.add('hidden');
    document.getElementById('tableCount').textContent = `共 ${liveRecordCount} 条`;
}

// ---- 查看历史结果 ----
async function viewResult(cid) {
    currentConvoId = cid;
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    liveRecordCount = 0;

    const res = await fetch(`/api/conversation/${cid}/status`);
    const s = await res.json();
    renderHistory(await (await fetch('/api/conversations')).json());
    showResultView(s.topic || s.title || '调研');

    if (s.status === 'error') {
        showError(s.error || '处理出错');
    } else {
        // running, pending, or done — all use the same polling to load records
        startPolling(cid);
    }
}

// ---- 导航 ----
function showResultView(title) {
    document.getElementById('inputView').classList.add('hidden');
    document.getElementById('resultView').classList.remove('hidden');
    document.getElementById('resultTitle').textContent = title || '调研中...';
    document.getElementById('statusCard').classList.remove('hidden');
    document.getElementById('cancelBtn').classList.remove('hidden');
    document.getElementById('reportResult').classList.add('hidden');
    document.getElementById('errorCard').classList.add('hidden');
    document.getElementById('submitBtn').disabled = false;
}

function backToInput() {
    document.getElementById('inputView').classList.remove('hidden');
    document.getElementById('resultView').classList.add('hidden');
    document.getElementById('topicInput').value = '';
    document.getElementById('submitBtn').disabled = false;
    currentConvoId = null;
    liveRecordCount = 0;
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    loadHistory();
}

function updateStatusText(text) {
    document.getElementById('statusText').textContent = text;
}

function showError(msg) {
    document.getElementById('statusCard').classList.add('hidden');
    document.getElementById('cancelBtn').classList.add('hidden');
    const errEl = document.getElementById('errorCard');
    errEl.classList.remove('hidden');
    document.getElementById('errorText').textContent = msg;
}

async function retryCurrent() {
    if (!currentConvoId) return;
    document.getElementById('errorCard').classList.add('hidden');
    document.getElementById('statusCard').classList.remove('hidden');
    document.getElementById('cancelBtn').classList.remove('hidden');
    updateStatusText('重新提交调研...');
    try { await fetch(`/api/conversation/${currentConvoId}/reset`, { method: 'POST' }); } catch(e) {}
    try { await fetch('/api/worker', { method: 'POST' }); } catch(e) {}
    startPolling(currentConvoId);
}

async function cancelResearch() {
    if (!currentConvoId) return;
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    if (!confirm('确定要终止当前调研吗？')) { startPolling(currentConvoId); return; }

    const btn = document.getElementById('cancelBtn');
    btn.disabled = true; btn.textContent = '⏳ 正在终止...';
    try {
        const res = await fetch(`/api/conversation/${currentConvoId}/cancel`, { method: 'POST' });
        const data = await res.json();
        if (data.ok) {
            showError('调研已被用户手动终止');
            loadHistory();
        } else {
            showError('终止失败: ' + (data.error || '未知错误'));
            startPolling(currentConvoId);
        }
    } catch (e) {
        showError('网络错误: ' + e.message);
        startPolling(currentConvoId);
    } finally {
        btn.disabled = false; btn.textContent = '⏹ 终止调研';
    }
}

function escapeHtml(s) {
    const d = document.createElement('div'); d.textContent = s; return d.innerHTML;
}

async function clearAllRecords() {
    if (!confirm('确定要清空所有调研记录吗？\n\n此操作不可撤销。')) return;
    try {
        const res = await fetch('/api/clear-all', { method: 'POST' });
        const data = await res.json();
        if (data.ok) { backToInput(); loadHistory(); alert(`✅ 已清空 ${data.deleted} 条记录`); }
        else { alert('❌ 清空失败: ' + (data.error || '未知错误')); }
    } catch (e) { alert('❌ 网络错误: ' + e.message); }
}
