(() => {
  if (window.__WEB_CAPTURE_INSTALLED__) return;
  window.__WEB_CAPTURE_INSTALLED__ = true;

  const MAX_REQUESTS = 200;
  const MAX_BODY_BYTES = 2 * 1024 * 1024;
  const SESSION_KEY = '__WEB_CAPTURE_RECORDING_SESSION__';
  function loadSession() {
    try { return JSON.parse(sessionStorage.getItem(SESSION_KEY) || 'null') || {}; } catch { return {}; }
  }
  const persistedSession = loadSession();
  window.__capturedRequests = Array.isArray(persistedSession.requests) ? persistedSession.requests.slice(-MAX_REQUESTS) : [];
  window.__webCaptureRules = Array.isArray(persistedSession.rules) ? persistedSession.rules : [];
  window.__webCaptureState = persistedSession.state && typeof persistedSession.state === 'object' ? { ...persistedSession.state, isRecording: !!persistedSession.state.isRecording } : { isRecording: false, startedAt: null, endedAt: null, dropped: 0, filtered: 0, matched: 0, activeRuleNames: [], lastUrl: null };

  function persistSession(withRequests = true) {
    const payload = { rules: window.__webCaptureRules, state: window.__webCaptureState, requests: withRequests ? window.__capturedRequests.slice(-MAX_REQUESTS) : [] };
    try { sessionStorage.setItem(SESSION_KEY, JSON.stringify(payload)); }
    catch {
      try { sessionStorage.setItem(SESSION_KEY, JSON.stringify({ rules: window.__webCaptureRules, state: window.__webCaptureState, requests: [] })); } catch {}
    }
  }
  function clearPersistedSession() { try { sessionStorage.removeItem(SESSION_KEY); } catch {} }
  if (window.__webCaptureState.isRecording) persistSession(false);

  function truncateUtf8(text, maxBytes = MAX_BODY_BYTES) {
    if (text == null) return null;
    const value = typeof text === 'string' ? text : String(text);
    const blob = new Blob([value]);
    if (blob.size <= maxBytes) return value;
    return value.slice(0, Math.floor(maxBytes / 2)) + '\n...[truncated: body exceeds 2MB]';
  }
  function pushRecord(record) {
    if (!window.__webCaptureState.isRecording) return;
    window.__capturedRequests.push(enrichRecord(record));
    window.__webCaptureState.lastUrl = record.url;
    while (window.__capturedRequests.length > MAX_REQUESTS) { window.__capturedRequests.shift(); window.__webCaptureState.dropped += 1; }
    persistSession(true);
  }
  function headersToObject(headers) {
    const obj = {};
    try {
      if (!headers) return obj;
      if (headers instanceof Headers) headers.forEach((v, k) => obj[k] = v);
      else if (Array.isArray(headers)) headers.forEach(([k, v]) => obj[k] = v);
      else if (typeof headers === 'object') Object.assign(obj, headers);
    } catch {}
    return obj;
  }
  function normalizeUrl(url) { try { return new URL(String(url), location.href).href; } catch { return String(url || ''); } }

  function parseRawHeaders(raw) {
    const obj = {};
    try {
      String(raw || '').trim().split(/[\r\n]+/).forEach((line) => {
        const idx = line.indexOf(':');
        if (idx <= 0) return;
        const key = line.slice(0, idx).trim();
        const value = line.slice(idx + 1).trim();
        if (!key) return;
        if (obj[key]) obj[key] = `${obj[key]}, ${value}`;
        else obj[key] = value;
      });
    } catch {}
    return obj;
  }
  function xhrResponseHeaders(xhr) {
    try { return parseRawHeaders(xhr.getAllResponseHeaders && xhr.getAllResponseHeaders()); } catch { return {}; }
  }
  function enrichRecord(record) {
    const reqHeaders = record.requestHeaders || {};
    const respHeaders = record.responseHeaders || {};
    return {
      ...record,
      requestHeaders: reqHeaders,
      responseHeaders: respHeaders,
      requestBody: record.requestBody ?? null,
      responseBody: record.responseBody ?? null,
      requestHeaderCount: Object.keys(reqHeaders).length,
      responseHeaderCount: Object.keys(respHeaders).length,
      requestBodySize: record.requestBody ? new Blob([String(record.requestBody)]).size : 0,
      responseBodySize: record.responseBody ? new Blob([String(record.responseBody)]).size : 0,
    };
  }
  function bodyToString(body) {
    if (body == null) return null;
    if (typeof body === 'string') return truncateUtf8(body);
    if (body instanceof URLSearchParams) return truncateUtf8(body.toString());
    if (body instanceof FormData) {
      const parts = [];
      body.forEach((v, k) => parts.push(`${k}=${v instanceof File ? `[File:${v.name},${v.size}]` : v}`));
      return truncateUtf8(parts.join('&'));
    }
    try { return truncateUtf8(JSON.stringify(body)); } catch { return truncateUtf8(String(body)); }
  }

  const SEARCH_KEYS = ['keyword','keywords','search','searchword','search_word','searchkeyword','search_keyword','query','q','wd','key','term','word','text'];
  function normalizeSearchKey(key) { return String(key || '').replace(/[_\-\s]/g, '').toLowerCase(); }
  function pickSearchFromObject(obj, depth = 0) {
    if (!obj || typeof obj !== 'object' || depth > 3) return null;
    for (const [k, v] of Object.entries(obj)) {
      if (SEARCH_KEYS.includes(normalizeSearchKey(k)) && v != null && typeof v !== 'object') return String(v).trim() || null;
    }
    for (const v of Object.values(obj)) {
      if (v && typeof v === 'object') { const hit = pickSearchFromObject(v, depth + 1); if (hit) return hit; }
    }
    return null;
  }
  function pickSearchFromUrl(url) {
    try {
      const u = new URL(url, location.href);
      for (const [k, v] of u.searchParams.entries()) if (SEARCH_KEYS.includes(normalizeSearchKey(k)) && v) return v.trim();
    } catch {}
    return null;
  }
  function pickSearchFromBody(body) {
    if (!body) return null;
    try { const obj = JSON.parse(body); const hit = pickSearchFromObject(obj); if (hit) return hit; } catch {}
    try {
      const qs = new URLSearchParams(body);
      for (const [k, v] of qs.entries()) if (SEARCH_KEYS.includes(normalizeSearchKey(k)) && v) return v.trim();
    } catch {}
    return null;
  }
  function pickSearchFromPage() {
    const selectors = [
      'input[type="search"]', 'input[name*="keyword" i]', 'input[name*="search" i]', 'input[name="q"]',
      'input[placeholder*="搜索"]', 'input[placeholder*="关键词"]', 'textarea[name*="keyword" i]'
    ];
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el && typeof el.value === 'string' && el.value.trim()) return el.value.trim();
    }
    return null;
  }
  function extractSearchKeyword(url, requestBody) { return pickSearchFromUrl(url) || pickSearchFromBody(requestBody) || pickSearchFromPage(); }


  const JSONP_CALLBACK_KEYS = ['callback', 'cb', 'jsonp', 'jsoncallback', 'jsonpcallback'];
  const jsonpWrapped = new Map();
  const jsonpPending = new Map();
  function extractJsonpCallback(url) {
    try {
      const u = new URL(url, location.href);
      for (const key of JSONP_CALLBACK_KEYS) {
        const name = u.searchParams.get(key);
        if (name && /^[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*$/.test(name)) return name;
      }
    } catch {}
    return null;
  }
  function getCallbackOwner(name) {
    const parts = String(name || '').split('.').filter(Boolean);
    if (!parts.length) return null;
    let owner = window;
    for (let i = 0; i < parts.length - 1; i += 1) {
      owner = owner?.[parts[i]];
      if (!owner) return null;
    }
    return { owner, prop: parts[parts.length - 1] };
  }
  function safeJson(value) {
    try { return JSON.stringify(value); } catch { return String(value); }
  }
  function completeJsonpRecord(callbackName, args) {
    const queue = jsonpPending.get(callbackName) || [];
    const pending = queue.shift();
    if (!pending || pending.done) return;
    pending.done = true;
    maybePush({ ...pending.record, responseStatus: 200, responseHeaders: {}, responseBody: truncateUtf8(safeJson(args.length === 1 ? args[0] : args)), duration: Math.round(performance.now() - pending.started) });
  }
  function wrapJsonpCallback(callbackName) {
    if (!callbackName || jsonpWrapped.has(callbackName)) return;
    const target = getCallbackOwner(callbackName);
    if (!target) return;
    let current = target.owner[target.prop];
    const makeWrapper = (fn) => function webCaptureJsonpWrapper(...args) {
      completeJsonpRecord(callbackName, args);
      if (typeof fn === 'function') return fn.apply(this, args);
      return undefined;
    };
    try {
      Object.defineProperty(target.owner, target.prop, {
        configurable: true,
        enumerable: true,
        get() { return current; },
        set(fn) { current = typeof fn === 'function' && !fn.__webCaptureJsonpWrapped ? makeWrapper(fn) : fn; if (current && typeof current === 'function') current.__webCaptureJsonpWrapped = true; }
      });
      if (typeof current === 'function') target.owner[target.prop] = current;
      jsonpWrapped.set(callbackName, true);
    } catch {
      if (typeof current === 'function' && !current.__webCaptureJsonpWrapped) {
        const wrapped = makeWrapper(current); wrapped.__webCaptureJsonpWrapped = true; target.owner[target.prop] = wrapped; jsonpWrapped.set(callbackName, true);
      }
    }
  }
  function trackScriptRequest(script) {
    if (!script || script.__webCaptureTracked) return;
    const src = script.src || script.getAttribute?.('src');
    if (!src || !window.__webCaptureState.isRecording) return;
    script.__webCaptureTracked = true;
    const url = normalizeUrl(src);
    const callbackName = extractJsonpCallback(url);
    const started = performance.now();
    const timestamp = Date.now();
    const requestHeaders = {};
    const requestBody = null;
    const baseRecord = { method: 'GET', url, requestHeaders, requestBody, responseHeaders: {}, searchKeyword: extractSearchKeyword(url, requestBody), timestamp, requestType: callbackName ? 'JSONP' : 'SCRIPT' };
    if (callbackName) {
      wrapJsonpCallback(callbackName);
      const queue = jsonpPending.get(callbackName) || [];
      queue.push({ record: baseRecord, started, done: false });
      jsonpPending.set(callbackName, queue);
    }
    script.addEventListener('load', () => {
      setTimeout(() => {
        if (callbackName) {
          const queue = jsonpPending.get(callbackName) || [];
          const pending = queue.find(x => x.record === baseRecord && !x.done);
          if (!pending) return;
          pending.done = true;
        }
        maybePush({ ...baseRecord, responseStatus: 200, responseHeaders: {}, responseBody: callbackName ? '[JSONP loaded, callback payload was not observed]' : '[SCRIPT loaded, response body unavailable]', duration: Math.round(performance.now() - started) });
      }, 0);
    }, { once: true });
    script.addEventListener('error', () => {
      maybePush({ ...baseRecord, responseStatus: 0, responseHeaders: {}, responseBody: '[SCRIPT load error]', duration: Math.round(performance.now() - started) });
    }, { once: true });
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
  function expandNestedJsonValues(obj) {
    const out = { ...(obj || {}) };
    for (const [k, v] of Object.entries(obj || {})) {
      if (typeof v !== 'string') continue;
      const text = v.trim();
      if (!text || !['{', '['].includes(text[0])) continue;
      try { out[k] = JSON.parse(text); } catch {}
    }
    return out;
  }
  function parseBodyObject(body) {
    if (!body) return {};
    try { return expandNestedJsonValues(JSON.parse(body)); } catch {}
    try { const obj = {}; new URLSearchParams(body).forEach((v,k)=>obj[k]=v); return expandNestedJsonValues(obj); } catch {}
    return {};
  }
  function paramsForMatch(url, body) { return { ...parse_query_for_rule(url), ...parseBodyObject(body) }; }
  function parse_query_for_rule(url) { const obj = {}; try { new URL(url, location.href).searchParams.forEach((v,k)=>obj[k]=v); } catch {} return expandNestedJsonValues(obj); }
  function safeDecodeUrlText(value) {
    try { return decodeURIComponent(String(value || '')); } catch { return String(value || ''); }
  }
  function ruleUrlMatch(url, rule) {
    const pattern = String(rule?.url_pattern || '').trim();
    const targetUrl = String(url || '').trim();
    const decodedUrl = safeDecodeUrlText(targetUrl);
    const decodedPattern = safeDecodeUrlText(pattern);
    if (!pattern) return false;
    if (rule.url_match_type === 'equals') return targetUrl === pattern || decodedUrl === decodedPattern;
    if (rule.url_match_type === 'regex') { try { const re = new RegExp(pattern); return re.test(targetUrl) || re.test(decodedUrl); } catch { return false; } }
    return targetUrl.includes(pattern) || decodedUrl.includes(pattern) || decodedUrl.includes(decodedPattern);
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
  function findRule(method, url, requestBody) {
    const rules = Array.isArray(window.__webCaptureRules) ? window.__webCaptureRules : [];
    if (!rules.length) return null;
    const params = paramsForMatch(url, requestBody);
    return rules.find(rule => Number(rule.enabled ?? 1) === 1 && (!rule.method || String(rule.method).toUpperCase() === method) && ruleUrlMatch(url, rule) && ruleParamsMatch(params, rule.params_filter)) || null;
  }
  function maybePush(record) {
    const rules = Array.isArray(window.__webCaptureRules) ? window.__webCaptureRules : [];
    const rule = findRule(record.method, record.url, record.requestBody);
    if (rules.length && !rule) { window.__webCaptureState.filtered += 1; return; }
    if (rule) { record.matchedRuleId = rule.id; record.matchedRuleName = rule.name; window.__webCaptureState.matched += 1; }
    pushRecord(record);
  }

  function statePayload() { return { ...window.__webCaptureState, count: window.__capturedRequests.length, max: MAX_REQUESTS }; }
  function startRecording() {
    window.__capturedRequests = [];
    const ruleNames = Array.isArray(window.__webCaptureRules) ? window.__webCaptureRules.map(r => r.name).filter(Boolean).slice(0, 8) : [];
    window.__webCaptureState = { isRecording: true, startedAt: new Date().toISOString(), endedAt: null, dropped: 0, filtered: 0, matched: 0, activeRuleNames: ruleNames, lastUrl: null };
    persistSession(false);
    return statePayload();
  }
  function stopRecording() {
    window.__webCaptureState.isRecording = false;
    window.__webCaptureState.endedAt = new Date().toISOString();
    persistSession(true);
    return statePayload();
  }
  function clearRequests() {
    window.__capturedRequests = [];
    window.__webCaptureState = { isRecording: false, startedAt: null, endedAt: null, dropped: 0, filtered: 0, matched: 0, activeRuleNames: [], lastUrl: null };
    clearPersistedSession();
    return statePayload();
  }

  const originalFetch = window.fetch;
  window.fetch = async function(input, init = {}) {
    const shouldCapture = window.__webCaptureState.isRecording;
    const started = performance.now(); const timestamp = Date.now();
    const req = input instanceof Request ? input : null;
    const url = normalizeUrl(typeof input === 'string' ? input : input?.url);
    const method = (init.method || req?.method || 'GET').toUpperCase();
    const requestHeaders = { ...headersToObject(req?.headers), ...headersToObject(init.headers) };
    let requestBody = bodyToString(init.body);
    if (shouldCapture && requestBody == null && req) { try { requestBody = truncateUtf8(await req.clone().text()); } catch {} }
    try {
      const response = await originalFetch.apply(this, arguments);
      if (shouldCapture) {
        const responseHeaders = headersToObject(response.headers);
        response.clone().text().then((text) => maybePush({ method, url, requestHeaders, requestBody, responseStatus: response.status, responseHeaders, searchKeyword: extractSearchKeyword(url, requestBody), responseBody: truncateUtf8(text), duration: Math.round(performance.now() - started), timestamp })).catch(() => maybePush({ method, url, requestHeaders, requestBody, responseStatus: response.status, responseHeaders, searchKeyword: extractSearchKeyword(url, requestBody), responseBody: '[unreadable response body]', duration: Math.round(performance.now() - started), timestamp }));
      }
      return response;
    } catch (error) {
      if (shouldCapture) maybePush({ method, url, requestHeaders, requestBody, responseStatus: 0, responseHeaders: {}, searchKeyword: extractSearchKeyword(url, requestBody), responseBody: String(error), duration: Math.round(performance.now() - started), timestamp });
      throw error;
    }
  };

  const XHR = XMLHttpRequest.prototype;
  const originalOpen = XHR.open, originalSend = XHR.send, originalSetHeader = XHR.setRequestHeader;
  XHR.open = function(method, url) { this.__webCapture = { method: String(method || 'GET').toUpperCase(), url: normalizeUrl(url), requestHeaders: {}, timestamp: Date.now(), started: performance.now(), shouldCapture: window.__webCaptureState.isRecording }; return originalOpen.apply(this, arguments); };
  XHR.setRequestHeader = function(name, value) { if (this.__webCapture) this.__webCapture.requestHeaders[name] = value; return originalSetHeader.apply(this, arguments); };
  XHR.send = function(body) {
    const meta = this.__webCapture || { method: 'GET', url: '', requestHeaders: {}, timestamp: Date.now(), started: performance.now(), shouldCapture: window.__webCaptureState.isRecording };
    meta.requestBody = bodyToString(body);
    this.addEventListener('loadend', () => {
      if (!meta.shouldCapture) return;
      let responseBody = '';
      try { responseBody = this.responseType && this.responseType !== 'text' ? `[${this.responseType} response]` : this.responseText; } catch { responseBody = '[unreadable response body]'; }
      maybePush({ method: meta.method, url: meta.url, requestHeaders: meta.requestHeaders, requestBody: meta.requestBody, responseStatus: this.status, responseHeaders: xhrResponseHeaders(this), searchKeyword: extractSearchKeyword(meta.url, meta.requestBody), responseBody: truncateUtf8(responseBody), duration: Math.round(performance.now() - meta.started), timestamp: meta.timestamp });
    });
    return originalSend.apply(this, arguments);
  };

  // CDP Network 模式已经能捕获 script/jsonp 网络请求；fallback 注入模式只保留 fetch/XHR，避免污染页面 DOM append/insert 行为。

  window.addEventListener('message', (event) => {
    if (event.source !== window || event.data?.source !== 'WEB_CAPTURE_CONTENT') return;
    const { action, requestId } = event.data;
    let payload;
    if (action === 'startRecording') { window.__webCaptureRules = Array.isArray(event.data.rules) ? event.data.rules : []; payload = startRecording(); }
    else if (action === 'restoreRecording') {
      const session = event.data.session || {};
      window.__webCaptureRules = Array.isArray(session.rules) ? session.rules : window.__webCaptureRules;
      window.__capturedRequests = Array.isArray(session.requests) ? session.requests.slice(-MAX_REQUESTS) : window.__capturedRequests;
      window.__webCaptureState = session.state && typeof session.state === 'object' ? { ...window.__webCaptureState, ...session.state, isRecording: !!session.state.isRecording } : window.__webCaptureState;
      persistSession(true);
      payload = statePayload();
    }
    else if (action === 'stopRecording') payload = stopRecording();
    else if (action === 'clearRequests') payload = clearRequests();
    else if (action === 'getState') payload = statePayload();
    else payload = { requests: [...window.__capturedRequests], state: statePayload() };
    window.postMessage({ source: 'WEB_CAPTURE_PAGE', requestId, payload }, '*');
  });
})();
