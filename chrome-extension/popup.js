const GLOBAL_CONFIG = window.WEB_CAPTURE_CONFIG || {};
function normalizeConfiguredUrl(raw, fallbackPort) {
  try {
    const url = new URL(raw || `http://localhost:${fallbackPort}`);
    if (url.hostname === '0.0.0.0') url.hostname = 'localhost';
    return url.toString().replace(/\/$/, '');
  } catch { return raw; }
}
const API = normalizeConfiguredUrl(GLOBAL_CONFIG.API_BASE || 'http://0.0.0.0:3088', '3088');
const WEB = normalizeConfiguredUrl(GLOBAL_CONFIG.WEB_BASE || 'http://0.0.0.0:3090', '3090');
let mode = 'login';
let recording = false;
let pollTimer = null;
let durationTimer = null;
let currentState = {};
let liveRequests = [];
let liveRequestsSignature = '';
let liveOpenKeys = new Set();
let activeRules = [];
let lastRenderedCount = 0;
let liveSearchKeyword = '';
let selectedLiveKey = '';
let selectedLiveRecord = null;
let autoRunPollingTimer = null;
let autoRunState = { running: false, count: 0, max: 0, mode: 'scroll' };
let autoRunErrorHandled = false;
const $ = (id) => document.getElementById(id);
const storage = { get: (k) => chrome.storage.local.get(k), set: (v) => chrome.storage.local.set(v), remove: (k) => chrome.storage.local.remove(k) };
function applyTheme(theme = 'auto') {
  const root = document.documentElement;
  if (theme === 'auto') root.removeAttribute('data-theme'); else root.setAttribute('data-theme', theme);
  const btn = $('themeBtn'); if (btn) btn.textContent = theme === 'dark' ? '☾' : theme === 'light' ? '☀' : '◐';
}
async function toggleTheme() {
  const { theme } = await storage.get('theme');
  const next = !theme || theme === 'auto' ? 'light' : theme === 'light' ? 'dark' : 'auto';
  await storage.set({ theme: next }); applyTheme(next); showToast(next === 'auto' ? '已跟随系统主题' : next === 'dark' ? '已切换深色主题' : '已切换浅色主题', 'info');
}
function setStatusPill(status) {
  const pill = $('statusPill'); if (!pill) return;
  const label = status === 'recording' ? 'Recording' : status === 'uploading' ? 'Uploading' : status === 'ready' ? 'Ready' : 'Idle';
  pill.className = `status-pill ${status}`; pill.querySelector('b').textContent = label;
}
function pulseCount(nextCount) {
  const pulse = $('recordPulse'), plus = $('plusOne'); if (!pulse) return;
  pulse.classList.remove('bump'); void pulse.offsetWidth; pulse.classList.add('bump');
  if (nextCount > lastRenderedCount && plus) { plus.classList.remove('hidden'); plus.classList.remove('plus-one'); void plus.offsetWidth; plus.classList.add('plus-one'); setTimeout(()=>plus.classList.add('hidden'), 720); }
  lastRenderedCount = nextCount;
}
function setUploading(active) { $('uploadProgress')?.classList.toggle('hidden', !active); $('recordPulse')?.classList.toggle('uploading', active); setStatusPill(active ? 'uploading' : (recording ? 'recording' : 'ready')); }
function shake(el) { if (!el) return; el.classList.remove('shake'); void el.offsetWidth; el.classList.add('shake'); }

function maskPhone(phone = '') { return phone.replace(/^(\+?\d{3})\d+(\d{4})$/, '$1****$2'); }
function showToast(text, type = 'ok') { const el = $('toast'); el.textContent = text; el.className = `toast ${type}`; clearTimeout(showToast.timer); showToast.timer = setTimeout(() => el.classList.add('hidden'), 3000); }
function setLoading(btn, loading, text) { btn.classList.toggle('loading', loading); btn.disabled = loading; btn.querySelector('.spinner')?.classList.toggle('hidden', !loading); if (text) btn.querySelector('.btn-text').textContent = text; }
function validateForm() { const phone = $('phone').value.trim(), password = $('password').value, confirm = $('confirmPassword').value; $('phoneError').textContent = /^\+?\d{5,20}$/.test(phone) ? '' : '请输入 5-20 位数字手机号'; $('passwordError').textContent = password.length >= 6 ? '' : '密码至少 6 位'; $('confirmError').textContent = mode === 'register' && password !== confirm ? '两次密码不一致' : ''; return !$('phoneError').textContent && !$('passwordError').textContent && !$('confirmError').textContent; }
async function init() { const { token, user, theme } = await storage.get(['token', 'user', 'theme']); applyTheme(theme || 'auto'); token ? showMain(user) : showAuth(); }
function showAuth() { stopPolling(); stopAutoRunPolling(); setStatusPill('idle'); $('authView').classList.remove('hidden'); $('mainView').classList.add('hidden'); $('logoutBtn').classList.add('hidden'); }
function showMain(user) { $('authView').classList.add('hidden'); $('mainView').classList.remove('hidden'); $('logoutBtn').classList.remove('hidden'); setStatusPill('ready'); renderAutoRunState(); syncAutoRunState(); const phone = user?.phone || ''; $('avatar').textContent = phone.slice(-2) || 'U'; $('helloText').textContent = `Hi，${maskPhone(phone) || 'User'}`; $('userInfo').textContent = `ID ${user?.id || '-'} · 已连接`; syncState(); }
function setMode(m) { const card = $('authView'); card.classList.remove('switching'); void card.offsetWidth; card.classList.add('switching'); mode = m; $('loginTab').classList.toggle('active', m === 'login'); $('registerTab').classList.toggle('active', m === 'register'); $('confirmWrap').classList.toggle('hidden', m !== 'register'); $('authTitle').textContent = m === 'login' ? '欢迎回来' : '创建账号'; $('authDesc').textContent = m === 'login' ? '登录后手动记录当前网页接口' : '注册后即可使用接口记录功能'; $('authSubmit').querySelector('.btn-text').textContent = m === 'login' ? '登录' : '注册'; $('authSwitch').innerHTML = m === 'login' ? '没有账号？<a href="#">立即注册</a>' : '已有账号？<a href="#">返回登录</a>'; $('authSwitch').querySelector('a').onclick = (e) => { e.preventDefault(); setMode(mode === 'login' ? 'register' : 'login'); }; ['phoneError','passwordError','confirmError'].forEach(id => $(id).textContent = ''); }
async function auth() { if (!validateForm()) return; const btn = $('authSubmit'); setLoading(btn, true, mode === 'login' ? '登录中...' : '注册中...'); try { const phone = $('phone').value.trim(), password = $('password').value; const res = await fetch(`${API}/api/user/${mode}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ phone, password }) }); const data = await res.json(); if (!res.ok || data.code !== 0) throw new Error(data.detail || data.message || '请求失败'); if (mode === 'register') { setMode('login'); showToast('注册成功，请登录'); return; } const user = data.user || { id: data.userId, phone: data.phone }; await storage.set({ token: data.token, user }); $('loginCheck')?.classList.remove('hidden'); setTimeout(()=>$('loginCheck')?.classList.add('hidden'), 900); showMain(user); showToast('登录成功'); } catch (e) { showToast(e.message, 'err'); } finally { setLoading(btn, false, mode === 'login' ? '登录' : '注册'); } }
async function activeTab() { const [tab] = await chrome.tabs.query({ active: true, currentWindow: true }); return tab; }
async function fetchRules(token){ try { const res = await fetch(`${API}/api/rules/list?enabledOnly=true&selectedOnly=true`, { headers: { 'Authorization': `Bearer ${token}` } }); const data = await res.json(); activeRules = Array.isArray(data.data) ? data.data : []; return activeRules; } catch { activeRules = []; return []; } }

async function runtimeMessage(message) { return await chrome.runtime.sendMessage(message); }
async function startNetworkRecording(tab, rules) { const res = await runtimeMessage({ action: 'cdpStartRecording', tabId: tab.id, rules }); if (!res?.ok) throw new Error(res?.error || 'Network 调试模式启动失败'); return { state: res.state || {} }; }
async function stopNetworkRecording(tab) { const res = await runtimeMessage({ action: 'cdpStopRecording', tabId: tab.id }); if (!res?.ok) throw new Error(res?.error || 'Network 调试模式停止失败'); return { state: res.state || {} }; }
async function getNetworkCaptured(tab) { const res = await runtimeMessage({ action: 'cdpGetCapturedRequests', tabId: tab.id }); if (!res?.ok) throw new Error(res?.error || '读取 Network 记录失败'); return res; }
async function getNetworkState(tab) { const res = await runtimeMessage({ action: 'cdpGetRecordingState', tabId: tab.id }); if (!res?.ok) throw new Error(res?.error || '读取 Network 状态失败'); return res; }
async function clearNetworkCaptured(tab) { const res = await runtimeMessage({ action: 'cdpClearCapturedRequests', tabId: tab.id }); if (!res?.ok) throw new Error(res?.error || '清空 Network 记录失败'); return res; }

async function sendToTabWithAutoInject(tab, message) { try { return await chrome.tabs.sendMessage(tab.id, message); } catch (err) { if (!tab.id || !tab.url || /^(chrome|edge|about|chrome-extension):/i.test(tab.url)) throw err; await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['content.js'] }); await new Promise(r => setTimeout(r, 300)); return await chrome.tabs.sendMessage(tab.id, message); } }
async function sendAutoRunMessage(action, options) { const tab = await activeTab(); return await sendToTabWithAutoInject(tab, { action, options }); }
function renderAutoRunState(state = autoRunState) {
  autoRunState = state || { running: false, count: 0, max: 0, mode: 'scroll' };
  const btn = $('autoRunBtn'), status = $('autoRunStatus');
  if (btn) btn.textContent = autoRunState.running ? '停止触发' : '自动下滑';
  if (btn) btn.classList.toggle('primary', !!autoRunState.running);
  if (btn) btn.classList.toggle('secondary', !autoRunState.running);
  if (status) status.textContent = autoRunState.running ? `${autoRunState.mode === 'next' ? '翻页' : autoRunState.mode === 'both' ? '下滑+翻页' : '下滑'} ${autoRunState.count || 0}/${autoRunState.max || '-'}${autoRunState.message ? ' · '+autoRunState.message : ''}` : (autoRunState.message || (autoRunState.selectedNextSelector ? '已选择翻页按钮' : '未开启'));
  if (autoRunState.status === 'error' && autoRunState.message) showToast(autoRunState.message, 'err');
}
function startAutoRunPolling(){ stopAutoRunPolling(); autoRunPollingTimer=setInterval(syncAutoRunState, 1000); }
function stopAutoRunPolling(){ if(autoRunPollingTimer) clearInterval(autoRunPollingTimer); autoRunPollingTimer=null; }
async function syncAutoRunState(){ try{ const res=await sendAutoRunMessage('getAutoRunState'); renderAutoRunState(res?.state || {}); if(res?.state?.running) startAutoRunPolling(); else stopAutoRunPolling(); if(res?.state?.status==='error' && recording && !autoRunErrorHandled){ autoRunErrorHandled=true; const tab=await activeTab(); try{ await stopNetworkRecording(tab); }catch{ try{ await sendToTabWithAutoInject(tab,{action:'stopRecording'}); }catch{} } await syncState(); showToast('自动翻页失败，已停止记录，数据已保留可上报', 'err'); }}catch{} }
async function toggleAutoRun(){
  try {
    if (autoRunState.running) { const res=await sendAutoRunMessage('stopAutoRun'); renderAutoRunState(res?.state || {}); stopAutoRunPolling(); showToast('已停止自动触发','info'); return; }
    if (!recording) return showToast('请先开始记录，再开启自动下滑/翻页', 'err');
    const mode = $('autoRunMode')?.value || 'scroll';
    const interval = Number($('autoRunInterval')?.value || 2500);
    const max = Number($('autoRunMax')?.value || 20);
    autoRunErrorHandled=false; const res=await sendAutoRunMessage('startAutoRun', { mode, interval, max, nextSelector:autoRunState.selectedNextSelector });
    renderAutoRunState(res?.state || {}); startAutoRunPolling(); showToast('自动触发已开始','info');
  } catch(e) { showToast(e.message || String(e), 'err'); }
}
async function pickNextButton(){
  try {
    const res = await sendAutoRunMessage('pickNextButton');
    renderAutoRunState(res?.state || {});
    showToast('请在页面中点击下一页按钮，Esc 可取消', 'info');
  } catch(e) { showToast(e.message || String(e), 'err'); }
}

function fmtDuration(startedAt){ if(!startedAt) return '00:00'; const sec=Math.max(0, Math.floor((Date.now()-new Date(startedAt).getTime())/1000)); const m=String(Math.floor(sec/60)).padStart(2,'0'); const s=String(sec%60).padStart(2,'0'); return `${m}:${s}`; }
function renderDuration(){ const el = $('recordDuration'); if (!el) return; el.textContent = currentState.isRecording ? fmtDuration(currentState.startedAt) : (currentState.startedAt && currentState.endedAt ? fmtDuration(currentState.startedAt).replace(/^/, '已记录 ') : '00:00'); }
function startDurationTimer(){ stopDurationTimer(); durationTimer=setInterval(renderDuration,1000); }
function stopDurationTimer(){ if(durationTimer) clearInterval(durationTimer); durationTimer=null; }
function escapeHtml(value){ return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch])); }
function compactText(value, len = 120){ const text = typeof value === 'string' ? value : JSON.stringify(value ?? ''); const oneLine = text.replace(/\s+/g, ' ').trim(); return oneLine.length > len ? `${oneLine.slice(0, len)}...` : oneLine; }
function tryJson(value){
  if (!value || typeof value !== 'string') return null;
  const text = value.trim();
  try { return JSON.parse(text); } catch {}
  const jsonp = text.match(/^[\w$.]+\((.*)\)\s*;?$/s);
  if (jsonp) { try { return JSON.parse(jsonp[1]); } catch {} }
  const first = text.indexOf('{'), last = text.lastIndexOf('}');
  if (first >= 0 && last > first) { try { return JSON.parse(text.slice(first, last + 1)); } catch {} }
  return null;
}
function pretty(value){ if (value == null || value === '') return '-'; if (typeof value === 'string') { const obj = tryJson(value); return obj ? JSON.stringify(obj, null, 2) : value; } try { return JSON.stringify(value, null, 2); } catch { return String(value); } }
function copyText(text){ const value = String(text || ''); if (!value) return showToast('没有可复制的内容', 'err'); try { navigator.clipboard?.writeText(value).then(()=>showToast('已复制')).catch(()=>fallbackCopy(value)); } catch { fallbackCopy(value); } }
function fallbackCopy(value){ const ta=document.createElement('textarea'); ta.value=value; ta.style.position='fixed'; ta.style.left='-9999px'; document.body.appendChild(ta); ta.focus(); ta.select(); try{document.execCommand('copy'); showToast('已复制');}catch{showToast('复制失败，请手动复制','err');} ta.remove(); }
function shellQuote(value){ return `'${String(value ?? '').replace(/'/g, `'"'"'`)}'`; }
function buildCurl(r){ const lines=[`curl ${shellQuote(r.url || '')}`]; const method=String(r.method || 'GET').toUpperCase(); if (method && method !== 'GET') lines.push(`  -X ${shellQuote(method)}`); Object.entries(r.requestHeaders || {}).forEach(([k,v])=>{ if (!/^(:|host$|content-length$)/i.test(k)) lines.push(`  -H ${shellQuote(`${k}: ${v}`)}`); }); if (r.requestBody) lines.push(`  --data-raw ${shellQuote(r.requestBody)}`); return lines.join(' \\\n'); }
function firstArray(obj, depth=0){
  if (!obj || typeof obj !== 'object' || depth > 6) return null;
  if (Array.isArray(obj)) return obj;
  for (const v of Object.values(obj)) {
    if (typeof v === 'string') { const parsed = tryJson(v); const hitFromString = firstArray(parsed, depth + 1); if (hitFromString) return hitFromString; }
    const hit = firstArray(v, depth+1); if (hit) return hit;
  }
  return null;
}
function productPreview(r){ const bodyObj = tryJson(r.responseBody || ''); const arr = firstArray(bodyObj); const item = arr?.find(x=>x && typeof x==='object') || (bodyObj && typeof bodyObj==='object' ? bodyObj : null); if (!item || typeof item !== 'object') return null; const fields = [['标题', item.title || item.name || item.item_title], ['店铺', item.nick || item.shopName || item.shop_name || item.shopInfo?.title], ['商品ID', item.item_id || item.itemId || item.id || item.sku_id], ['价格', item.priceShow?.price || item.price || item.salePrice], ['销量', item.realSales || item.sales || item.sold], ['关键词', inferSearchKeyword(r)]]; return fields.filter(([,v])=>v!=null && String(v).trim()).slice(0, 8); }
function showLiveDetailByKey(key){ const record = liveRequests.find(r => requestKey(r) === key); if (!record) return; selectedLiveKey = key; selectedLiveRecord = record; renderLiveDetail(record); }
function closeLiveDetail(){ selectedLiveKey=''; selectedLiveRecord=null; const panel=$('liveDetailPanel'); if(panel) panel.classList.add('hidden'); document.querySelectorAll('.live-row.active').forEach(el=>el.classList.remove('active')); }
function renderLiveDetail(r){ const panel=$('liveDetailPanel'); if(!panel) return; const key=requestKey(r); document.querySelectorAll('.live-row.active').forEach(el=>el.classList.toggle('active', el.dataset.key===key)); const preview=productPreview(r); const curl=buildCurl(r); panel.classList.remove('hidden'); panel.innerHTML=`<div class="detail-sheet-head"><div><b>接口详情</b><span>${escapeHtml(r.method || 'GET')} · ${escapeHtml(r.responseStatus ?? '-')} · ${escapeHtml(r.duration ?? '-')}ms</span></div><button class="sheet-close" data-action="close-detail">×</button></div>${preview?`<div class="product-preview"><b>抓取结果</b>${preview.map(([k,v])=>`<div><span>${escapeHtml(k)}</span><strong>${escapeHtml(compactText(v,80))}</strong></div>`).join('')}</div>`:''}<div class="detail-actions-row"><button data-copy="url">复制 URL</button><button data-copy="headers">复制请求头</button><button data-copy="body">复制请求体</button><button data-copy="response">复制 Response</button><button data-copy="curl">复制 cURL</button></div><div class="detail-section"><b>URL</b><pre>${escapeHtml(r.url || '-')}</pre></div><div class="detail-section"><b>Request Headers</b><pre>${escapeHtml(pretty(r.requestHeaders || {}))}</pre></div><div class="detail-section"><b>Request Body</b><pre>${escapeHtml(pretty(r.requestBody))}</pre></div><div class="detail-section"><b>Response</b><pre>${escapeHtml(pretty(r.responseBody))}</pre></div><div class="detail-section"><b>cURL</b><pre>${escapeHtml(curl)}</pre></div>`; panel.querySelector('[data-action="close-detail"]')?.addEventListener('click', closeLiveDetail); panel.querySelectorAll('[data-copy]').forEach(btn=>btn.addEventListener('click',()=>{ const type=btn.dataset.copy; const map={url:r.url,headers:pretty(r.requestHeaders||{}),body:r.requestBody,response:pretty(r.responseBody),curl}; copyText(map[type] || ''); })); }

function decodeKeywordText(value){ try { return decodeURIComponent(String(value || '').replace(/\+/g, ' ')); } catch { return String(value || ''); } }
function inferSearchKeyword(r){ if (r.searchKeyword) return decodeKeywordText(r.searchKeyword); try { const u = new URL(r.url || ''); for (const key of ['keyword','keywords','search','search_word','searchKeyword','query','q','wd','key','term','word']) { const v = u.searchParams.get(key); if (v) return decodeKeywordText(v); } } catch {} try { const obj = JSON.parse(r.requestBody || ''); const stack = [obj]; const keys = new Set(['keyword','keywords','search','searchword','searchkeyword','query','q','wd','key','term','word']); while (stack.length) { const cur = stack.pop(); if (!cur || typeof cur !== 'object') continue; for (const [k,v] of Object.entries(cur)) { const nk = k.replace(/[\s_-]/g,'').toLowerCase(); if (keys.has(nk) && v != null && typeof v !== 'object') return decodeKeywordText(v); if (v && typeof v === 'object') stack.push(v); } } } catch {} return ''; }
function methodClass(method){ return `method-${String(method || 'GET').toLowerCase()}`; }
function statusClass(status){ const s = Number(status || 0); if (!s) return 'status-err'; if (s >= 500) return 'status-5xx'; if (s >= 400) return 'status-4xx'; if (s >= 300) return 'status-3xx'; return 'status-2xx'; }
function requestKey(r){ return `${r.timestamp || ''}|${r.method || ''}|${r.url || ''}|${r.responseStatus ?? ''}|${r.duration ?? ''}|${r.responseBody ? String(r.responseBody).length : 0}`; }
function requestsSignature(requests = []){ return requests.map(requestKey).join('@@'); }
function updateLiveStats(requests = []) {
  const stats = $('liveStats'); if (!stats) return;
  const ok = requests.filter(r => Number(r.responseStatus || 0) >= 200 && Number(r.responseStatus || 0) < 300).length;
  const fail = requests.filter(r => Number(r.responseStatus || 0) >= 400).length;
  const slow = requests.filter(r => Number(r.duration || 0) >= 1000).length;
  stats.innerHTML = `<span>成功 ${ok}</span><span>失败 ${fail}</span><span>慢 ${slow}</span>`;
}
function matchLiveSearch(r, keyword) {
  if (!keyword) return true;
  const k = keyword.toLowerCase();
  return [r.url, r.method, r.requestBody, r.responseBody, r.matchedRuleName, inferSearchKeyword(r)].some(v => String(v || '').toLowerCase().includes(k));
}
function renderLiveRequests(requests = [], force = false) {
  if (force) { liveRequestsSignature = ''; selectedLiveKey = ''; selectedLiveRecord = null; closeLiveDetail(); }
  const nextRequests = Array.isArray(requests) ? requests : [];
  const nextSignature = requestsSignature(nextRequests);
  $('liveHint').textContent = nextRequests.length ? `已捕获 ${nextRequests.length} 个` : (recording ? '等待页面发起接口...' : '开始记录后实时展示');
  if (!force && nextSignature === liveRequestsSignature) return;
  liveRequests = nextRequests;
  liveRequestsSignature = nextSignature;
  updateLiveStats(liveRequests);
  const list = $('liveList');
  if (!list) return;
  const shownRequests = liveRequests.filter(r => matchLiveSearch(r, liveSearchKeyword));
  if (!liveRequests.length) {
    list.className = 'live-list empty';
    list.textContent = recording ? '记录中，但当前还没有新接口。请在网页里搜索、翻页或点击触发请求。' : '暂无接口。点击“开始记录”后，在页面中搜索、翻页或点击触发接口。';
    return;
  }
  if (!shownRequests.length) { list.className = 'live-list empty'; list.textContent = `有 ${liveRequests.length} 个接口，但没有命中当前搜索关键词。`; return; }
  list.className = 'live-list result-mode';
  const rows = shownRequests.slice().reverse().slice(0, 120).map((r) => {
    const url = r.url || '-';
    let hostPath = url;
    try { const u = new URL(url); hostPath = `${u.host}${u.pathname}`; } catch {}
    const searchKeyword = inferSearchKeyword(r);
    const time = r.timestamp ? new Date(r.timestamp).toLocaleTimeString() : '';
    const key = requestKey(r);
    const ok = Number(r.responseStatus || 0) >= 200 && Number(r.responseStatus || 0) < 300;
    return `<div class="live-row ${selectedLiveKey === key ? 'active' : ''}" data-key="${escapeHtml(key)}">
      <div class="live-row-main">
        <span class="live-method ${methodClass(r.method)}">${escapeHtml(r.method || 'GET')}</span>
        <span class="live-url" title="${escapeHtml(url)}">${escapeHtml(hostPath)}</span>
        <span class="live-status ${statusClass(r.responseStatus)}">${escapeHtml(r.responseStatus ?? '-')}</span>
      </div>
      <div class="live-row-sub"><span>${escapeHtml(time)}</span><span>${escapeHtml(r.duration ?? '-')} ms</span><span>ReqH ${escapeHtml(r.requestHeaderCount ?? Object.keys(r.requestHeaders || {}).length)}</span><span>ResH ${escapeHtml(r.responseHeaderCount ?? Object.keys(r.responseHeaders || {}).length)}</span>${r.matchedRuleName ? `<span class="live-rule">规则：${escapeHtml(r.matchedRuleName)}</span>` : ''}${searchKeyword ? `<span class="live-keyword">${escapeHtml(searchKeyword)}</span>` : ''}<button class="detail-btn ${ok ? 'ok' : 'warn'}" data-detail-key="${escapeHtml(key)}">查看详情</button></div>
    </div>`;
  }).join('');
  list.innerHTML = rows;
  list.querySelectorAll('[data-detail-key]').forEach(btn => btn.addEventListener('click', (e) => { e.stopPropagation(); showLiveDetailByKey(btn.dataset.detailKey); }));
  list.querySelectorAll('.live-row').forEach(row => row.addEventListener('click', () => showLiveDetailByKey(row.dataset.key)));
  if (selectedLiveKey && !liveRequests.find(r => requestKey(r) === selectedLiveKey)) closeLiveDetail();
}
function renderState(state = {}) {
  currentState = state || {};
  recording = !!state.isRecording;
  const count = state.count || 0;
  const countEl = $('recordCount');
  if (countEl && Number(countEl.textContent || 0) !== count) pulseCount(count);
  if (countEl) countEl.textContent = count;
  $('recordPulse')?.classList.toggle('recording', recording);
  $('recordPulse')?.classList.toggle('idle', !recording);
  $('recordPulse')?.classList.toggle('uploading', false);
  setStatusPill(recording ? 'recording' : 'ready');
  const matched = state.matched || 0;
  const filtered = state.filtered || 0;
  const dropped = state.dropped || 0;
  if ($('recordTitle')) $('recordTitle').textContent = recording ? `正在记录 · ${count} 个接口` : count ? `已停止 · ${count} 个待上报` : '空闲，等待开始记录';
  if ($('recordDesc')) $('recordDesc').textContent = recording ? '保持侧边栏打开，在页面里搜索、翻页或点击。' : '一轮记录结束后可直接上报到 WebPC。';
  if ($('recordStats')) $('recordStats').textContent = `命中 ${matched} · 过滤 ${filtered}${dropped ? ` · 丢弃 ${dropped}` : ''}`;
  if ($('captureNote')) {
    const modeText = state.captureMode ? `模式：${state.captureMode}` : 'Network 模式可拿到更完整的 headers / body。';
    const ruleText = Array.isArray(state.activeRuleNames) && state.activeRuleNames.length ? `规则：${state.activeRuleNames.slice(0, 2).join(' / ')}${state.activeRuleNames.length > 2 ? ' 等' : ''}` : modeText;
    $('captureNote').textContent = recording ? ruleText : '点击开始后，Chrome 可能提示“正在调试此网页”，这是正常的 Network 捕获。';
  }
  renderDuration();
  recording ? startDurationTimer() : stopDurationTimer();
  if ($('startBtn')) $('startBtn').disabled = recording;
  if ($('stopUploadBtn')) $('stopUploadBtn').disabled = !count && !recording;
  if ($('discardBtn')) $('discardBtn').disabled = !count && !recording;
}
function startPolling(){ stopPolling(); pollTimer = setInterval(syncState, 1000); }
function stopPolling(){ if (pollTimer) clearInterval(pollTimer); pollTimer = null; stopDurationTimer(); }
async function syncState(){ try { const tab = await activeTab(); let res; try { res = await getNetworkState(tab); } catch { res = await sendToTabWithAutoInject(tab, { action: 'getRecordingState' }); } renderState(res?.state || {}); renderLiveRequests(res?.xhrList || res?.state?.requests || liveRequests); if (res?.state?.isRecording) startPolling(); } catch {} }

async function startRecording(){
  const { token } = await storage.get('token');
  if (!token) return showAuth();
  const btn = $('startBtn');
  setLoading(btn, true, '准备中...');
  try {
    const tab = await activeTab();
    const rules = await fetchRules(token);
    let res;
    let captureMode = 'CDP Network';
    try {
      res = await startNetworkRecording(tab, rules);
    } catch (networkErr) {
      captureMode = '页面注入';
      res = await sendToTabWithAutoInject(tab, { action: 'startRecording', rules });
      showToast(`Network 模式不可用，已回退：${networkErr.message}`, 'err');
    }
    renderState({ ...(res?.state || {}), captureMode });
    renderLiveRequests([], true);
    await storage.set({ [`recording_${tab.id}`]: { startedAt: res?.state?.startedAt, tabId: tab.id, url: tab.url, captureMode } });
    if ($('captureNote')) $('captureNote').textContent = `已开始：${captureMode} · 规则 ${activeRules.length} 条${activeRules.length ? ' · 仅记录命中接口' : ' · 记录全部 Fetch/XHR'}`;
    showToast(captureMode === 'CDP Network' ? 'Network 调试模式已开始' : '页面注入模式已开始', 'info');
    startPolling();
    setTimeout(syncState, 120);
  } catch(e) {
    shake(btn);
    showToast(e.message, 'err');
    if ($('captureNote')) $('captureNote').textContent = `启动失败：${e.message}`;
  } finally {
    setLoading(btn, false, '开始记录');
  }
}

async function stopAndUpload(){ try{ await sendAutoRunMessage('stopAutoRun'); renderAutoRunState({running:false,count:0,max:0,mode:'scroll'}); stopAutoRunPolling(); }catch{} const { token } = await storage.get('token'); if (!token) return showAuth(); const btn = $('stopUploadBtn'); setUploading(true); setLoading(btn, true, '上报中...'); try { const tab = await activeTab(); let payload; try { await stopNetworkRecording(tab); payload = await getNetworkCaptured(tab); } catch { await sendToTabWithAutoInject(tab, { action: 'stopRecording' }); payload = await sendToTabWithAutoInject(tab, { action: 'getCapturedRequests' }); } if (!payload.pageUrl) { payload.pageUrl = tab.url; payload.pageTitle = tab.title; } renderLiveRequests(payload?.xhrList || [], true); const xhrCount = payload?.xhrList?.length || 0; if (!xhrCount) throw new Error('本次记录没有捕获到接口'); const body = { pageUrl: payload.pageUrl || payload.url || tab.url, pageTitle: payload.pageTitle || payload.title || tab.title, htmlContent: payload.htmlContent, startedAt: payload.startedAt, endedAt: payload.endedAt || new Date().toISOString(), xhrList: payload.xhrList }; const res = await fetch(`${API}/api/capture/upload`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` }, body: JSON.stringify(body) }); const data = await res.json(); if (res.status === 401) { await storage.remove(['token', 'user']); showAuth(); throw new Error('登录已过期，请重新登录'); } if (!res.ok || data.code !== 0) throw new Error(data.detail || data.message || '上传失败'); try { await clearNetworkCaptured(tab); } catch { await sendToTabWithAutoInject(tab, { action: 'clearCapturedRequests' }); } await storage.remove(`recording_${tab.id}`); lastRenderedCount = 0; renderState({}); renderLiveRequests([], true); stopPolling(); if ($('captureNote')) $('captureNote').textContent = `上报成功：${data.insertedCount ?? data.apiCount ?? xhrCount} 个接口 · 会话 ${data.sessionId || '-'}`; showToast('上报成功'); } catch(e){ shake(btn); if ($('captureNote')) $('captureNote').textContent = `上报失败：${e.message}，数据已保留，可重试。`; showToast(e.message, 'err'); await syncState(); } finally { setUploading(false); setLoading(btn, false, '停止并上报'); } }

async function discardRecording(){ try { await sendAutoRunMessage('stopAutoRun').catch(()=>{}); renderAutoRunState({running:false,count:0,max:0,mode:'scroll'}); stopAutoRunPolling(); const tab = await activeTab(); try { await clearNetworkCaptured(tab); } catch { await sendToTabWithAutoInject(tab, { action: 'clearCapturedRequests' }); } await storage.remove(`recording_${tab.id}`); lastRenderedCount = 0; renderState({}); renderLiveRequests([], true); stopPolling(); if ($('captureNote')) $('captureNote').textContent = '已放弃本次记录，缓存已清空。'; showToast('已放弃记录'); } catch(e){ showToast(e.message, 'err'); } }

$('loginTab').onclick = () => setMode('login'); $('registerTab').onclick = () => setMode('register'); $('authSwitch').querySelector('a').onclick = (e) => { e.preventDefault(); setMode('register'); }; ['phone','password','confirmPassword'].forEach(id => $(id).addEventListener('input', () => { if ($(id).value) validateForm(); }));
function addRipple(btn){ btn.addEventListener('click', (e)=>{ const r=btn.getBoundingClientRect(); btn.style.setProperty('--ripple-x', `${e.clientX-r.left}px`); btn.style.setProperty('--ripple-y', `${e.clientY-r.top}px`); btn.classList.remove('ripple'); void btn.offsetWidth; btn.classList.add('ripple'); }); }
document.querySelectorAll('.btn,.capture-btn,.icon-btn').forEach(addRipple);
$('liveSearch')?.addEventListener('input', (e)=>{ liveSearchKeyword = e.target.value.trim(); renderLiveRequests(liveRequests, true); });
$('themeBtn').onclick = toggleTheme; $('authSubmit').onclick = auth; $('startBtn').onclick = startRecording; $('autoRunBtn').onclick = toggleAutoRun; $('pickNextBtn').onclick = pickNextButton; $('stopUploadBtn').onclick = stopAndUpload; $('discardBtn').onclick = discardRecording; $('webBtn').onclick = () => chrome.tabs.create({ url: WEB });
async function logout(){ const view = $('mainView'); view.classList.add('fade-out'); await new Promise(r=>setTimeout(r,260)); await storage.remove(['token', 'user']); view.classList.remove('fade-out'); showAuth(); showToast('已登出'); }
$('logoutBtn').onclick = logout; init();
