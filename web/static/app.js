const API = '/api';

let state = {
    platforms: {},
    currentPlatform: null,
    conversations: [],
    currentCid: null,
    messages: [],
    msgOffset: 0,
    convKeyword: '',
};

// ─── 初始化 ──────────────────────────────────────────────────

init();
async function init() {
    await loadPlatforms();
    setupEventListeners();
}

// ─── 平台管理 ──────────────────────────────────────────────────

async function loadPlatforms() {
    try {
        const res = await fetch(API + '/platforms');
        const data = await res.json();
        state.platforms = data.platforms || {};
        renderPlatformTabs();
        const avail = Object.entries(state.platforms).filter(([_, p]) => p.available);
        if (avail.length) switchPlatform(avail[0][0]);
    } catch (e) {
        console.error('加载平台失败:', e);
        showToast('加载平台列表失败', 'error');
    }
}

function renderPlatformTabs() {
    const tabs = document.getElementById('platformTabs');
    tabs.innerHTML = '';
    for (const [name, p] of Object.entries(state.platforms)) {
        const tab = document.createElement('button');
        tab.className = 'platform-tab' + (state.currentPlatform === name ? ' active' : '');
        const availIcon = p.available ? '✓' : '✗';
        const availClass = p.available ? 'yes' : 'no';
        tab.innerHTML = `${p.display_name} <span class="avail ${availClass}">${availIcon}</span>`;
        tab.onclick = () => switchPlatform(name);
        tabs.appendChild(tab);
    }
}

async function switchPlatform(name) {
    state.currentPlatform = name;
    state.currentCid = null;
    state.messages = [];
    state.msgOffset = 0;
    document.getElementById('msgList').innerHTML = '<div class="loading">加载中...</div>';
    document.getElementById('msgHeader').innerHTML = '<span>请选择一个会话</span>';
    document.getElementById('msgActions').style.display = 'none';
    document.getElementById('msgFooter').style.display = 'none';
    renderPlatformTabs();
    await loadConversations();
}

// ─── 会话列表 ──────────────────────────────────────────────────

async function loadConversations() {
    const list = document.getElementById('convList');
    list.innerHTML = '<div class="loading">加载中...</div>';
    const name = state.currentPlatform;
    if (!name) { list.innerHTML = '<div class="loading">请先选择平台</div>'; return; }

    const kw = state.convKeyword ? '&keyword=' + encodeURIComponent(state.convKeyword) : '';
    try {
        const res = await fetch(API + '/platforms/' + name + '/conversations?limit=5000' + kw);
        const data = await res.json();
        state.conversations = data.conversations || [];
        document.getElementById('sidebarFooter').textContent = '共 ' + state.conversations.length + ' 个会话';
        if (data.error) document.getElementById('sidebarFooter').textContent += ' (' + data.error + ')';
        renderConversations();
    } catch (e) {
        list.innerHTML = '<div class="loading">加载失败: ' + e.message + '</div>';
    }
}

function renderConversations() {
    const list = document.getElementById('convList');
    if (!state.conversations.length) {
        list.innerHTML = '<div class="empty-state"><div class="empty-icon">📭</div><p>暂无会话</p></div>';
        return;
    }
    list.innerHTML = '';
    for (const c of state.conversations) {
        const item = document.createElement('div');
        item.className = 'conv-item' + (state.currentCid === c.cid ? ' active' : '');
        item.dataset.cid = c.cid;
        const icon = c.type === 'group' ? '👥' : '👤';
        const badge = c.unread_count > 0 ? '<span class="conv-badge">' + c.unread_count + '</span>' : '';
        const top = c.is_top ? '📌 ' : '';
        item.innerHTML = '<div class="conv-title">' + badge + top + icon + ' ' + escapeHtml(c.title) + '</div>' +
            '<div class="conv-meta">' + (c.platform || state.currentPlatform) + '</div>';
        item.onclick = () => selectConversation(c.cid);
        list.appendChild(item);
    }
}

// ─── 消息加载 ──────────────────────────────────────────────────

async function selectConversation(cid) {
    state.currentCid = cid;
    state.messages = [];
    state.msgOffset = 0;
    renderConversations();
    const conv = state.conversations.find(c => c.cid === cid);
    const title = conv ? conv.title : '消息';
    const icon = conv && conv.type === 'group' ? '👥' : '👤';
    document.getElementById('msgHeader').innerHTML = '<span>' + icon + ' ' + escapeHtml(title) + '</span><div class="msg-actions" id="msgActions"><button class="btn-ai" onclick="showAIAnalysis()">🤖 AI 分析</button></div>';
    await loadMessages(true);
}

async function loadMessages(reset) {
    const container = document.getElementById('msgList');
    if (reset) container.innerHTML = '<div class="loading">加载中...</div>';
    const name = state.currentPlatform;
    const cid = state.currentCid;
    if (!cid) return;
    try {
        const res = await fetch(API + '/platforms/' + name + '/conversations/' + cid + '/messages?limit=50&offset=' + state.msgOffset);
        const data = await res.json();
        const msgs = data.messages || [];
        if (reset) state.messages = msgs;
        else state.messages = state.messages.concat(msgs);
        state.msgOffset += msgs.length;
        renderMessages();
        document.getElementById('msgFooter').style.display = msgs.length >= 50 ? 'block' : 'none';
    } catch (e) {
        container.innerHTML = '<div class="loading">加载失败: ' + e.message + '</div>';
    }
}

function renderMessages() {
    const container = document.getElementById('msgList');
    if (!state.messages.length) {
        container.innerHTML = '<div class="empty-state"><div class="empty-icon">📭</div><p>暂无消息</p></div>';
        return;
    }
    container.innerHTML = '';
    for (const m of state.messages) {
        const item = document.createElement('div');
        const isSelf = m.sender_name === '我' || m.sender_id === 'me';
        item.className = 'msg-item ' + (isSelf ? 'self' : 'other');
        const time = m.timestamp ? new Date(m.timestamp).toLocaleString('zh-CN') : '';
        const sender = m.sender_name || (isSelf ? '我' : '未知');
        item.innerHTML =
            '<div class="msg-sender">' + escapeHtml(sender) + '</div>' +
            '<div class="msg-bubble">' + escapeHtml(m.content || '') + '</div>' +
            '<div class="msg-time">' + time + '</div>';
        container.appendChild(item);
    }
    container.scrollTop = container.scrollHeight;
}

function loadMore() { loadMessages(false); }

// ─── 搜索 ──────────────────────────────────────────────────

function toggleSearch() {
    const bar = document.getElementById('searchBar');
    bar.style.display = bar.style.display === 'none' ? 'flex' : 'none';
    if (bar.style.display !== 'none') document.getElementById('searchInput').focus();
}
function closeSearch() { document.getElementById('searchBar').style.display = 'none'; }

async function doSearch() {
    const q = document.getElementById('searchInput').value.trim();
    if (!q) return;
    const name = state.currentPlatform;
    if (!name) { showToast('请先选择平台', 'error'); return; }
    const container = document.getElementById('msgList');
    container.innerHTML = '<div class="loading">搜索中...</div>';
    try {
        const res = await fetch(API + '/platforms/' + name + '/search?q=' + encodeURIComponent(q) + '&limit=50');
        const data = await res.json();
        const msgs = data.messages || [];
        if (!msgs.length) {
            container.innerHTML = '<div class="empty-state"><p>未找到 "' + escapeHtml(q) + '" 的相关消息</p></div>';
            return;
        }
        document.getElementById('msgHeader').innerHTML = '<span>🔍 搜索: ' + escapeHtml(q) + ' (' + data.total + ' 条)</span>';
        state.messages = msgs;
        renderMessages();
    } catch (e) {
        container.innerHTML = '<div class="loading">搜索失败: ' + e.message + '</div>';
    }
}

function filterConversations() {
    state.convKeyword = document.getElementById('convSearch').value;
    loadConversations();
}

// ─── AI 分析 ──────────────────────────────────────────────────

async function showAIAnalysis() {
    if (!state.messages.length) {
        showToast('请先加载消息', 'error');
        return;
    }

    const modal = document.getElementById('aiModal');
    modal.style.display = 'flex';
    const content = document.getElementById('aiContent');
    content.innerHTML = '<div class="ai-loading"><div class="ai-spinner"></div><p>AI 正在分析聊天记录...</p><p class="hint">提取关键信息、识别维权要素、生成维权建议</p></div>';

    // 准备消息摘要
    const msgSummary = state.messages.slice(-200).map(m => {
        const time = m.timestamp ? new Date(m.timestamp).toLocaleString('zh-CN') : '';
        const sender = m.sender_name || '未知';
        return `[${time}] ${sender}: ${(m.content || '').slice(0, 200)}`;
    }).join('\n');

    const conv = state.conversations.find(c => c.cid === state.currentCid);
    const convTitle = conv ? conv.title : '未知会话';

    try {
        const res = await fetch(API + '/ai/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                conversation: convTitle,
                messages: msgSummary,
                platform: state.currentPlatform || '',
            }),
        });
        const data = await res.json();

        if (data.error) {
            content.innerHTML = '<div class="ai-result"><div class="error">❌ ' + escapeHtml(data.error) + '</div></div>';
        } else {
            content.innerHTML = '<div class="ai-result">' + renderAnalysisResult(data.result) + '</div>';
        }
    } catch (e) {
        content.innerHTML = '<div class="ai-result"><div class="error">❌ 分析失败: ' + escapeHtml(e.message) + '</div></div>';
    }
}

function renderAnalysisResult(r) {
    // 如果是旧格式（纯字符串），用旧方法渲染
    if (typeof r === 'string') return formatAIResult(r);

    const method = r.method === 'ai' ? '🤖 AI 智能分析' : '⚙️ 规则引擎分析';
    let html = '<div class="analysis-report">';

    // 头部
    html += '<div class="analysis-header"><span class="analysis-method">' + method + '</span></div>';

    // 案件类型
    const conf = Math.round((r.case_type_confidence || 0) * 100);
    html += '<div class="analysis-section">';
    html += '<h3>🎯 案件类型</h3>';
    html += '<div class="case-type-badge">' + escapeHtml(r.case_type || '未识别') + ' <span class="confidence">置信度 ' + conf + '%</span></div>';
    if (r.summary) html += '<p class="summary">' + escapeHtml(r.summary) + '</p>';
    html += '</div>';

    // 当事人
    if (r.parties && r.parties.length) {
        html += '<div class="analysis-section">';
        html += '<h3>👥 当事人</h3>';
        html += '<div class="parties-list">';
        for (const p of r.parties) {
            html += '<div class="party-item"><span class="party-name">' + escapeHtml(p.name) + '</span>';
            html += '<span class="party-role ' + (p.role === '受害者' ? 'victim' : '') + '">' + escapeHtml(p.role) + '</span></div>';
        }
        html += '</div></div>';
    }

    // 时间线
    if (r.timeline && r.timeline.length) {
        html += '<div class="analysis-section">';
        html += '<h3>📅 时间线</h3>';
        html += '<div class="timeline">';
        for (const t of r.timeline.slice(-10)) {
            const icon = t.importance === 'high' ? '🔴' : t.importance === 'medium' ? '🟡' : '⚪';
            html += '<div class="timeline-item ' + (t.importance || '') + '">';
            html += '<span class="tl-icon">' + icon + '</span>';
            html += '<span class="tl-date">' + escapeHtml(t.date) + '</span>';
            html += '<span class="tl-event">' + escapeHtml(t.event) + '</span>';
            html += '</div>';
        }
        html += '</div></div>';
    }

    // 关键事实
    if (r.key_facts && r.key_facts.length) {
        html += '<div class="analysis-section">';
        html += '<h3>🔍 关键事实</h3>';
        html += '<ul class="facts-list">';
        for (const f of r.key_facts) {
            const icon = f.importance === 'high' ? '❗' : '📌';
            html += '<li>' + icon + ' ' + escapeHtml(f.fact) + '</li>';
        }
        html += '</ul></div>';
    }

    // 证据分析
    if (r.evidence) {
        const ev = r.evidence;
        const strengthClass = ev.strength === '强' ? 'strong' : ev.strength === '中' ? 'medium' : 'weak';
        html += '<div class="analysis-section">';
        html += '<h3>📊 证据强度</h3>';
        html += '<div class="evidence-strength ' + strengthClass + '">' + escapeHtml(ev.strength || '未知') + '</div>';
        if (ev.items && ev.items.length) {
            html += '<div class="evidence-items">';
            for (const item of ev.items) {
                html += '<div class="ev-item ok">✅ <span class="ev-type">' + escapeHtml(item.type) + '</span> ' + escapeHtml(item.description) + '</div>';
            }
            html += '</div>';
        }
        if (ev.gaps && ev.gaps.length) {
            html += '<div class="evidence-gaps">';
            for (const gap of ev.gaps) {
                html += '<div class="ev-item gap">❌ 缺少: ' + escapeHtml(gap) + '</div>';
            }
            html += '</div>';
        }
        html += '</div>';
    }

    // 法律依据
    if (r.legal_basis && r.legal_basis.length) {
        html += '<div class="analysis-section">';
        html += '<h3>⚖️ 法律依据</h3>';
        html += '<ul class="laws-list">';
        for (const l of r.legal_basis) {
            html += '<li>《' + escapeHtml(l.law) + '》' + (l.article ? escapeHtml(l.article) : '') + '</li>';
        }
        html += '</ul></div>';
    }

    // 赔偿预期
    if (r.compensation) {
        html += '<div class="analysis-section">';
        html += '<h3>💰 赔偿/补偿预期</h3>';
        html += '<p class="compensation">' + escapeHtml(r.compensation) + '</p>';
        html += '</div>';
    }

    // 维权步骤
    if (r.action_plan && r.action_plan.length) {
        html += '<div class="analysis-section">';
        html += '<h3>📝 维权步骤</h3>';
        html += '<div class="action-steps">';
        for (const a of r.action_plan) {
            html += '<div class="step">';
            html += '<div class="step-num">' + a.step + '</div>';
            html += '<div class="step-content">';
            html += '<div class="step-title">' + escapeHtml(a.action) + '</div>';
            html += '<div class="step-detail">' + escapeHtml(a.detail) + '</div>';
            if (a.deadline) html += '<div class="step-meta">⏰ ' + escapeHtml(a.deadline) + '</div>';
            if (a.cost) html += '<div class="step-meta">💲 ' + escapeHtml(a.cost) + '</div>';
            html += '</div></div>';
        }
        html += '</div></div>';
    }

    // 风险提示
    if (r.risks && r.risks.length) {
        html += '<div class="analysis-section">';
        html += '<h3>⚠️ 风险提示</h3>';
        html += '<ul class="risks-list">';
        for (const risk of r.risks) {
            html += '<li>' + escapeHtml(risk) + '</li>';
        }
        html += '</ul></div>';
    }

    // 底部
    html += '<div class="analysis-footer">';
    html += '<p>本报告由' + (r.method === 'ai' ? 'AI 智能分析' : '规则引擎分析') + '生成，仅供参考。具体维权方案请咨询专业律师。</p>';
    html += '</div>';

    html += '</div>';
    return html;
}

function formatAIResult(text) {
    if (!text) return '<p>无分析结果</p>';
    // 简单的 Markdown 转 HTML
    return text
        .replace(/### (.+)/g, '<h3>$1</h3>')
        .replace(/## (.+)/g, '<h3>$1</h3>')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\n- /g, '\n<li>')
        .replace(/\n(\d+)\. /g, '\n<li>')
        .replace(/\n\n/g, '</p><p>')
        .replace(/\n/g, '<br>')
        .replace(/<li>/g, '</p><ul><li>')
        .replace(/<\/li>(?=<br>|<h3>|$)/g, '</li></ul>')
        ;
}

// ─── 导出 ──────────────────────────────────────────────────

function showExport() {
    document.getElementById('exportModal').style.display = 'flex';
    renderExportConvs();
}

function renderExportConvs() {
    const container = document.getElementById('exportConvList');
    const convs = state.conversations;
    if (!convs.length) {
        container.innerHTML = '<p class="hint" style="padding:16px">请先加载会话列表</p>';
        return;
    }
    container.innerHTML = '';
    const showConvs = convs.slice(0, 5000);
    for (const c of showConvs) {
        const icon = c.type === 'group' ? '👥' : '👤';
        const item = document.createElement('label');
        item.className = 'export-conv-item';
        item.dataset.cid = c.cid;
        item.dataset.title = c.title;
        item.innerHTML = '<input type="checkbox" value="' + escapeHtml(c.cid) + '" onchange="updateExportCount()"> ' +
            icon + ' ' + escapeHtml(c.title);
        container.appendChild(item);
    }
    if (convs.length > 5000) {
        const more = document.createElement('div');
        more.className = 'hint';
        more.style.padding = '8px 12px';
        more.textContent = '... 还有 ' + (convs.length - 5000) + ' 个会话未显示，请使用筛选功能';
        container.appendChild(more);
    }
    updateExportCount();
}

function filterExportConvs() {
    const keyword = document.getElementById('exportSearch').value.toLowerCase();
    const items = document.querySelectorAll('#exportConvList .export-conv-item');
    items.forEach(item => {
        const title = (item.dataset.title || '').toLowerCase();
        const cid = (item.dataset.cid || '').toLowerCase();
        item.style.display = (!keyword || title.includes(keyword) || cid.includes(keyword)) ? '' : 'none';
    });
}

function selectAllExport(checked) {
    const items = document.querySelectorAll('#exportConvList .export-conv-item');
    items.forEach(item => {
        if (item.style.display !== 'none') {
            const cb = item.querySelector('input[type="checkbox"]');
            if (cb) cb.checked = checked;
        }
    });
    updateExportCount();
}

function updateExportCount() {
    const checked = document.querySelectorAll('#exportConvList input[type="checkbox"]:checked');
    document.getElementById('exportSelectedCount').textContent = '已选 ' + checked.length + ' 个';
}

async function doExport() {
    const checkboxes = document.querySelectorAll('#exportConvList input[type="checkbox"]:checked');
    const cids = Array.from(checkboxes).map(cb => cb.value);
    if (!cids.length) { showToast('请至少选择一个会话', 'error'); return; }

    const statusEl = document.getElementById('exportStatus');
    statusEl.style.display = 'block';
    statusEl.className = 'export-status';
    statusEl.textContent = '正在导出 ' + cids.length + ' 个会话，请稍候...';
    showToast('正在导出 ' + cids.length + ' 个会话...', 'info');

    try {
        const res = await fetch(API + '/export', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ platform: state.currentPlatform, cids: cids }),
        });
        const data = await res.json();
        if (data.status === 'success') {
            statusEl.className = 'export-status success';
            statusEl.innerHTML = '✅ 导出成功！共 <b>' + data.count + '</b> 个会话<br>📁 ' + (data.export_dir || '');
            showToast('导出成功！', 'success');
        } else {
            throw new Error(data.detail || '导出失败');
        }
    } catch (e) {
        statusEl.className = 'export-status error';
        statusEl.textContent = '❌ 导出失败: ' + e.message;
        showToast('导出失败: ' + e.message, 'error');
    }
}

// ─── 导出历史 ──────────────────────────────────────────────────

async function showExports() {
    document.getElementById('exportsModal').style.display = 'flex';
    const container = document.getElementById('exportHistoryList');
    container.innerHTML = '<div class="loading">加载中...</div>';
    try {
        const res = await fetch(API + '/export/list');
        const data = await res.json();
        const exports = data.exports || [];
        if (!exports.length) {
            container.innerHTML = '<div class="empty-state"><div class="empty-icon">📭</div><p>暂无导出记录</p></div>';
            return;
        }
        container.innerHTML = '';
        for (const exp of exports) {
            const item = document.createElement('div');
            item.className = 'export-history-item';
            item.innerHTML =
                '<div><div class="export-name">📁 ' + escapeHtml(exp.name) + '</div>' +
                '<div class="export-meta">' + exp.size_str + (exp.has_json ? ' · 含JSON' : '') + '</div></div>' +
                '<div class="export-actions-bar">' +
                (exp.has_json ? '<button class="btn-sm primary" onclick="downloadExport(\'' + escapeHtml(exp.name) + '\')">下载</button>' : '') +
                '</div>';
            container.appendChild(item);
        }
    } catch (e) {
        container.innerHTML = '<div class="loading">加载失败: ' + e.message + '</div>';
    }
}

function downloadExport(name) {
    window.open(API + '/export/' + encodeURIComponent(name) + '/download', '_blank');
}

// ─── 导入 ──────────────────────────────────────────────────

function showImport() {
    document.getElementById('importModal').style.display = 'flex';
}

async function doImport() {
    const filePath = document.getElementById('importPath').value.trim();
    if (!filePath) { showToast('请输入文件路径', 'error'); return; }

    const statusEl = document.getElementById('importStatus');
    statusEl.style.display = 'block';
    statusEl.className = 'export-status';
    statusEl.textContent = '正在导入...';

    let platform = state.currentPlatform || '';
    if (filePath.toLowerCase().endsWith('.json')) platform = platform || 'qq';
    else if (filePath.toLowerCase().endsWith('.txt') || filePath.toLowerCase().endsWith('.csv')) platform = platform || 'qq';

    try {
        const res = await fetch(API + '/import', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ platform: platform, file_path: filePath }),
        });
        const data = await res.json();
        if (data.success) {
            statusEl.className = 'export-status success';
            statusEl.textContent = '✅ 导入成功！';
            showToast('导入成功！', 'success');
            await loadConversations();
        } else {
            throw new Error(data.detail || '导入失败');
        }
    } catch (e) {
        statusEl.className = 'export-status error';
        statusEl.textContent = '❌ ' + e.message;
        showToast('导入失败: ' + e.message, 'error');
    }
}

// ─── 通用 ──────────────────────────────────────────────────

function refresh() {
    loadConversations();
    showToast('已刷新', 'info');
}

function hideModal(id) { document.getElementById(id).style.display = 'none'; }
function closeModal(event, id) { if (event.target === event.currentTarget) hideModal(id); }

function showToast(message, type) {
    type = type || 'info';
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = 'toast ' + type;
    toast.style.display = 'block';
    setTimeout(() => { toast.style.display = 'none'; }, 3000);
}

function escapeHtml(t) {
    if (!t) return '';
    var d = document.createElement('div');
    d.textContent = t;
    return d.innerHTML;
}

function setupEventListeners() {
    document.getElementById('searchInput').addEventListener('keydown', function(e) {
        if (e.key === 'Enter') doSearch();
        if (e.key === 'Escape') closeSearch();
    });
}

// ─── AI 设置 ──────────────────────────────────────────────────

async function showSettings() {
    document.getElementById('settingsModal').style.display = 'flex';
    // 加载当前配置
    try {
        const res = await fetch(API + '/ai/config');
        const data = await res.json();
        document.getElementById('aiApiBase').value = data.api_base || '';
        document.getElementById('aiModel').value = data.model || '';
        // 不回填 key（安全），但显示状态
        const statusEl = document.getElementById('aiStatus');
        if (data.has_key) {
            statusEl.className = 'settings-status active';
            statusEl.innerHTML = '<span class="status-dot active"></span><span class="status-text">AI 已启用 (' + escapeHtml(data.model) + ')</span>';
        } else {
            statusEl.className = 'settings-status inactive';
            statusEl.innerHTML = '<span class="status-dot inactive"></span><span class="status-text">未配置 API Key，使用规则引擎</span>';
        }
    } catch (e) {
        console.error('加载 AI 配置失败:', e);
    }
}

function presetAI(provider) {
    const presets = {
        openai: { base: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
        deepseek: { base: 'https://api.deepseek.com/v1', model: 'deepseek-chat' },
        zhipu: { base: 'https://open.bigmodel.cn/api/paas/v4', model: 'glm-4-flash' },
        custom: { base: '', model: '' },
    };
    const p = presets[provider] || presets.custom;
    document.getElementById('aiApiBase').value = p.base;
    document.getElementById('aiModel').value = p.model;
}

async function saveAIConfig() {
    const apiKey = document.getElementById('aiApiKey').value.trim();
    const apiBase = document.getElementById('aiApiBase').value.trim();
    const model = document.getElementById('aiModel').value.trim();

    try {
        const res = await fetch(API + '/ai/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_key: apiKey, api_base: apiBase, model: model }),
        });
        const data = await res.json();
        if (data.has_key) {
            showToast('AI 配置已保存，AI 分析已启用！', 'success');
        } else {
            showToast('配置已保存（未填写 Key，使用规则引擎）', 'info');
        }
        hideModal('settingsModal');
        // 清空 key 输入框
        document.getElementById('aiApiKey').value = '';
    } catch (e) {
        showToast('保存失败: ' + e.message, 'error');
    }
}
