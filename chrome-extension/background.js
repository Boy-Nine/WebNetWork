const CDP_VERSION = '1.3';
const MAX_REQUESTS = 300;
const MAX_BODY_BYTES = 2 * 1024 * 1024;
const sessions = new Map();

chrome.runtime.onInstalled.addListener(async () => {
  if (chrome.sidePanel?.setPanelBehavior) await chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(console.warn);
});
chrome.runtime.onStartup?.addListener(async () => {
  if (chrome.sidePanel?.setPanelBehavior) await chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(console.warn);
});
chrome.action.onClicked.addListener(async (tab) => {
  if (chrome.sidePanel?.open && tab?.windowId) await chrome.sidePanel.open({ windowId: tab.windowId }).catch(console.warn);
});

function target(tabId) { return { tabId }; }
function send(tabId, method, params = {}) {
  return new Promise((resolve, reject) => chrome.debugger.sendCommand(target(tabId), method, params, (res) => chrome.runtime.lastError ? reject(new Error(chrome.runtime.lastError.message)) : resolve(res)));
}
function attach(tabId) {
  return new Promise((resolve, reject) => chrome.debugger.attach(target(tabId), CDP_VERSION, () => chrome.runtime.lastError ? reject(new Error(chrome.runtime.lastError.message)) : resolve()));
}
function detach(tabId) {
  return new Promise((resolve) => chrome.debugger.detach(target(tabId), () => { void chrome.runtime.lastError; resolve(); }));
}
function truncateText(value, maxBytes = MAX_BODY_BYTES) {
  if (value == null) return null;
  const text = typeof value === 'string' ? value : String(value);
  const size = new Blob([text]).size;
  if (size <= maxBytes) return text;
  return text.slice(0, Math.floor(maxBytes / 2)) + '\n...[truncated: body exceeds 2MB]';
}
function headersToObject(headers) {
  const out = {};
  try {
    if (!headers) return out;
    Object.entries(headers).forEach(([k, v]) => out[k] = Array.isArray(v) ? v.join(', ') : String(v));
  } catch {}
  return out;
}
function parseQuery(url) {
  const obj = {};
  try { new URL(url).searchParams.forEach((v, k) => obj[k] = v); } catch {}
  return obj;
}
function parseBodyObject(body) {
  if (!body) return {};
  try { return JSON.parse(body); } catch {}
  try { const obj = {}; new URLSearchParams(body).forEach((v,k)=>obj[k]=v); return obj; } catch {}
  return {};
}
function readPath(obj, path) {
  if (!path) return obj;
  let cur = obj;
  for (const part of String(path).split('.')) {
    if (!part) continue;
    if (cur == null) return undefined;
    cur = Array.isArray(cur) ? cur[Number(part)] : cur[part];
  }
  return cur;
}
function ruleUrlMatch(url, rule) {
  const pattern = String(rule?.url_pattern || '').trim();
  const targetUrl = String(url || '').trim();
  if (!pattern) return false;
  if (rule.url_match_type === 'equals') return targetUrl === pattern;
  if (rule.url_match_type === 'regex') { try { return new RegExp(pattern).test(targetUrl); } catch { return false; } }
  return targetUrl.includes(pattern);
}
function ruleParamsMatch(params, filter) {
  if (!filter || typeof filter !== 'object') return true;
  for (const [k, expected] of Object.entries(filter)) {
    const actual = readPath(params, k);
    if (actual == null) return false;
    if (expected != null && expected !== '' && !String(actual).includes(String(expected))) return false;
  }
  return true;
}
function findRule(method, url, requestBody, rules) {
  if (!Array.isArray(rules) || !rules.length) return null;
  const params = { ...parseQuery(url), ...parseBodyObject(requestBody) };
  return rules.find(rule => Number(rule.enabled ?? 1) === 1 && (!rule.method || String(rule.method).toUpperCase() === method) && ruleUrlMatch(url, rule) && ruleParamsMatch(params, rule.params_filter)) || null;
}
const SEARCH_KEYS = ['keyword','keywords','search','searchword','search_word','searchkeyword','search_keyword','query','q','wd','key','term','word','text'];
function normKey(k){ return String(k||'').replace(/[\s_-]/g,'').toLowerCase(); }
function pickSearch(obj, depth=0){
  if (!obj || typeof obj !== 'object' || depth > 5) return '';
  for (const [k,v] of Object.entries(obj)) if (SEARCH_KEYS.includes(normKey(k)) && v != null && typeof v !== 'object') return String(v);
  for (const v of Object.values(obj)) { const hit = pickSearch(v, depth+1); if (hit) return hit; }
  return '';
}
function searchKeyword(url, body) { return pickSearch(parseQuery(url)) || pickSearch(parseBodyObject(body)); }
function shouldKeepType(type, hasRules) {
  const t = String(type || '').toLowerCase();
  if (hasRules) return ['xhr','fetch','script','other'].includes(t);
  return ['xhr','fetch'].includes(t);
}
function statePayload(session) {
  return { isRecording: !!session?.isRecording, startedAt: session?.startedAt || null, endedAt: session?.endedAt || null, count: session?.requests?.length || 0, max: MAX_REQUESTS, matched: session?.matched || 0, filtered: session?.filtered || 0, dropped: session?.dropped || 0, lastUrl: session?.lastUrl || null, activeRuleNames: session?.rules?.map(r=>r.name).filter(Boolean).slice(0,8) || [], captureMode: 'CDP Network' };
}
function pushRecord(session, record) {
  if (!session?.isRecording) return;
  const rules = session.rules || [];
  const rule = findRule(record.method, record.url, record.requestBody, rules);
  if (rules.length && !rule) { session.filtered += 1; return; }
  if (!rules.length && !shouldKeepType(record.requestType, false)) { session.filtered += 1; return; }
  if (rule) { record.matchedRuleId = rule.id; record.matchedRuleName = rule.name; session.matched += 1; }
  const reqHeaders = record.requestHeaders || {}, respHeaders = record.responseHeaders || {};
  record.requestHeaderCount = Object.keys(reqHeaders).length;
  record.responseHeaderCount = Object.keys(respHeaders).length;
  record.requestBodySize = record.requestBody ? new Blob([String(record.requestBody)]).size : 0;
  record.responseBodySize = record.responseBody ? new Blob([String(record.responseBody)]).size : 0;
  session.requests.push(record);
  session.lastUrl = record.url;
  while (session.requests.length > MAX_REQUESTS) { session.requests.shift(); session.dropped += 1; }
}
async function startCdp(tabId, rules = []) {
  if (!tabId) throw new Error('缺少 tabId');
  if (sessions.has(tabId)) await stopCdp(tabId, false).catch(()=>{});
  await attach(tabId);
  await send(tabId, 'Network.enable', { maxResourceBufferSize: MAX_BODY_BYTES, maxTotalBufferSize: MAX_BODY_BYTES * 10 });
  await send(tabId, 'Network.setCacheDisabled', { cacheDisabled: false }).catch(()=>{});
  const session = { tabId, isRecording: true, startedAt: new Date().toISOString(), endedAt: null, rules: Array.isArray(rules) ? rules : [], requests: [], pending: new Map(), matched: 0, filtered: 0, dropped: 0, lastUrl: null };
  sessions.set(tabId, session);
  return statePayload(session);
}
async function stopCdp(tabId, doDetach = true) {
  const session = sessions.get(tabId);
  if (!session) return { isRecording: false, count: 0, captureMode: 'CDP Network' };
  session.isRecording = false;
  session.endedAt = new Date().toISOString();
  // 给 loadingFinished 的 getResponseBody 留一点尾巴时间。
  await new Promise(r => setTimeout(r, 180));
  if (doDetach) await detach(tabId).catch(()=>{});
  return statePayload(session);
}
function clearCdp(tabId) {
  const session = sessions.get(tabId);
  if (session) {
    session.requests = [];
    session.pending = new Map();
    session.isRecording = false;
    session.endedAt = new Date().toISOString();
    detach(tabId).catch(()=>{});
    sessions.delete(tabId);
  }
  return { isRecording: false, count: 0, captureMode: 'CDP Network' };
}
function getCdpPayload(tabId) {
  const session = sessions.get(tabId);
  if (!session) return { state: { isRecording: false, count: 0, captureMode: 'CDP Network' }, xhrList: [] };
  return { state: statePayload(session), xhrList: [...session.requests], startedAt: session.startedAt, endedAt: session.endedAt || new Date().toISOString() };
}
chrome.debugger.onEvent.addListener(async (source, method, params) => {
  const tabId = source.tabId;
  const session = sessions.get(tabId);
  if (!session) return;
  const pending = session.pending;
  if (method === 'Network.requestWillBeSent') {
    const req = params.request || {};
    const methodName = String(req.method || 'GET').toUpperCase();
    const requestBody = truncateText(req.postData || null);
    pending.set(params.requestId, {
      method: methodName,
      url: req.url || '',
      requestHeaders: headersToObject(req.headers),
      requestBody,
      responseStatus: null,
      responseHeaders: {},
      searchKeyword: searchKeyword(req.url, requestBody),
      responseBody: null,
      duration: null,
      timestamp: Date.now(),
      requestType: params.type || 'Other',
      wallTime: params.wallTime,
      startedTs: params.timestamp,
    });
  } else if (method === 'Network.requestWillBeSentExtraInfo') {
    const rec = pending.get(params.requestId);
    if (rec) rec.requestHeaders = { ...rec.requestHeaders, ...headersToObject(params.headers) };
  } else if (method === 'Network.responseReceived') {
    const rec = pending.get(params.requestId);
    if (rec) {
      rec.responseStatus = params.response?.status ?? null;
      rec.responseHeaders = { ...rec.responseHeaders, ...headersToObject(params.response?.headers) };
      rec.mimeType = params.response?.mimeType;
    }
  } else if (method === 'Network.responseReceivedExtraInfo') {
    const rec = pending.get(params.requestId);
    if (rec) {
      rec.responseStatus = params.statusCode ?? rec.responseStatus;
      rec.responseHeaders = { ...rec.responseHeaders, ...headersToObject(params.headers) };
    }
  } else if (method === 'Network.loadingFinished') {
    const rec = pending.get(params.requestId);
    if (!rec) return;
    pending.delete(params.requestId);
    rec.duration = rec.startedTs ? Math.round((params.timestamp - rec.startedTs) * 1000) : null;
    try {
      const body = await send(tabId, 'Network.getResponseBody', { requestId: params.requestId });
      rec.responseBody = truncateText(body?.base64Encoded ? `[base64 body omitted, ${body.body?.length || 0} chars]` : body?.body);
    } catch {
      rec.responseBody = rec.responseBody || '[response body unavailable]';
    }
    pushRecord(session, rec);
  } else if (method === 'Network.loadingFailed') {
    const rec = pending.get(params.requestId);
    if (!rec) return;
    pending.delete(params.requestId);
    rec.responseStatus = 0;
    rec.responseBody = params.errorText || '[request failed]';
    rec.duration = rec.startedTs && params.timestamp ? Math.round((params.timestamp - rec.startedTs) * 1000) : null;
    pushRecord(session, rec);
  }
});
chrome.debugger.onDetach.addListener((source) => {
  const session = sessions.get(source.tabId);
  if (session) { session.isRecording = false; session.endedAt = session.endedAt || new Date().toISOString(); }
});
chrome.tabs?.onRemoved?.addListener((tabId) => { sessions.delete(tabId); });

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    if (message?.action === 'ping') return { ok: true };
    if (message?.action === 'openSidePanel') { chrome.windows.getCurrent(async (win) => { if (chrome.sidePanel?.open && win?.id) await chrome.sidePanel.open({ windowId: win.id }).catch(console.warn); }); return { ok: true }; }
    if (message?.action === 'cdpStartRecording') return { ok: true, state: await startCdp(message.tabId, message.rules || []) };
    if (message?.action === 'cdpStopRecording') return { ok: true, state: await stopCdp(message.tabId) };
    if (message?.action === 'cdpGetCapturedRequests') return { ok: true, ...getCdpPayload(message.tabId) };
    if (message?.action === 'cdpGetRecordingState') return { ok: true, ...getCdpPayload(message.tabId) };
    if (message?.action === 'cdpClearCapturedRequests') return { ok: true, state: clearCdp(message.tabId) };
    return undefined;
  })().then((res) => { if (res !== undefined) sendResponse(res); }).catch((err) => sendResponse({ ok: false, error: err.message || String(err) }));
  return true;
});
