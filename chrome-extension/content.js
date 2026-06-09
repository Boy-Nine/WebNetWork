(function setupWebCaptureContentScript() {
  if (window.__WEB_CAPTURE_CONTENT_INSTALLED__) return;
  window.__WEB_CAPTURE_CONTENT_INSTALLED__ = true;

  let injected = false;
  function injectHook() {
    if (injected || document.getElementById('__web_capture_injected_script__')) {
      injected = true;
      return Promise.resolve();
    }
    return new Promise((resolve) => {
      const script = document.createElement('script');
      script.id = '__web_capture_injected_script__';
      script.src = chrome.runtime.getURL('injected.js');
      script.onload = () => { injected = true; script.remove(); resolve(); };
      script.onerror = () => resolve();
      (document.documentElement || document.head || document.body).appendChild(script);
    });
  }
  function askPage(action, extra = {}) {
    return new Promise((resolve) => {
      const requestId = `${Date.now()}-${Math.random()}`;
      const timer = setTimeout(() => { window.removeEventListener('message', handler); resolve(null); }, 1500);
      const handler = (event) => {
        if (event.source !== window || event.data?.source !== 'WEB_CAPTURE_PAGE' || event.data?.requestId !== requestId) return;
        clearTimeout(timer); window.removeEventListener('message', handler); resolve(event.data.payload);
      };
      window.addEventListener('message', handler);
      window.postMessage({ source: 'WEB_CAPTURE_CONTENT', action, requestId, ...extra }, '*');
    });
  }

  let autoRunTimer = null;
  let autoRunMissingSince = 0;
  let autoRunState = { running: false, count: 0, max: 0, mode: 'scroll', interval: 2500, lastHeight: 0, lastUrl: '', status: 'idle', message: '', selectedNextSelector: '' };
  const NEXT_SELECTOR_KEY = '__WEB_CAPTURE_NEXT_SELECTOR__';
  const NEXT_SELECTORS = [
    'a[rel="next"]', 'button[aria-label*="下一" i]', 'a[aria-label*="下一" i]',
    '.next:not(.disabled)', '.pagination-next:not(.disabled)', '.ant-pagination-next:not(.ant-pagination-disabled)',
    '.el-pagination .btn-next:not(:disabled)', '.pager-next:not(.disabled)'
  ];
  function cssPath(el) {
    if (!el || el.nodeType !== 1) return '';
    if (el.id) return `#${CSS.escape(el.id)}`;
    const parts = [];
    let cur = el;
    while (cur && cur.nodeType === 1 && cur !== document.body && cur !== document.documentElement) {
      let part = cur.localName.toLowerCase();
      const cls = Array.from(cur.classList || []).filter(Boolean).slice(0, 3);
      if (cls.length) part += cls.map(c => `.${CSS.escape(c)}`).join('');
      const parent = cur.parentElement;
      if (parent) {
        const siblings = Array.from(parent.children).filter(x => x.localName === cur.localName);
        if (siblings.length > 1) part += `:nth-of-type(${siblings.indexOf(cur) + 1})`;
      }
      parts.unshift(part);
      cur = parent;
      if (parts.length >= 5) break;
    }
    return parts.join(' > ');
  }
  function visible(el) {
    if (!el) return false;
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
  }
  function disabledLike(el) {
    const cls = String(el?.className || '').toLowerCase();
    return !!(el?.disabled || el?.getAttribute?.('aria-disabled') === 'true' || cls.includes('disabled') || cls.includes('disable'));
  }
  function getStoredNextSelector(){ try { return sessionStorage.getItem(NEXT_SELECTOR_KEY) || ''; } catch { return ''; } }
  function setStoredNextSelector(sel){ try { sessionStorage.setItem(NEXT_SELECTOR_KEY, sel || ''); } catch {} }
  function findNextButton() {
    const selected = autoRunState.selectedNextSelector || getStoredNextSelector();
    if (selected) {
      try { const el = document.querySelector(selected); if (visible(el) && !disabledLike(el)) return el; } catch {}
    }
    const textCandidates = Array.from(document.querySelectorAll('a,button,[role="button"],li,span')).filter(el => {
      const text = (el.innerText || el.textContent || el.getAttribute('aria-label') || '').trim();
      return visible(el) && !disabledLike(el) && /^(下一页?|Next|>|›|»)$|下一|next/i.test(text);
    });
    for (const el of textCandidates) return el.closest('button,a,[role="button"],li') || el;
    for (const sel of NEXT_SELECTORS) {
      const el = document.querySelector(sel);
      if (visible(el) && !disabledLike(el)) return el;
    }
    return null;
  }
  function stopAutoRun(message) {
    if (autoRunTimer) clearInterval(autoRunTimer);
    autoRunTimer = null;
    autoRunState.running = false;
    autoRunState.status = message ? 'error' : 'idle';
    if (message) autoRunState.message = message;
    return getAutoRunState();
  }
  function clickNextIfPossible() {
    const next = findNextButton();
    if (next) {
      autoRunMissingSince = 0;
      next.scrollIntoView({ block: 'center', inline: 'center', behavior: 'smooth' });
      setTimeout(() => next.click(), 160);
      autoRunState.message = '已点击下一页';
      return true;
    }
    autoRunMissingSince ||= Date.now();
    const waited = Date.now() - autoRunMissingSince;
    autoRunState.message = `未找到下一页按钮，已等待 ${Math.round(waited / 1000)}s`;
    if (waited >= 20000) stopAutoRun('20 秒内找不到下一页按钮，已停止自动触发');
    return false;
  }
  function autoRunStep() {
    if (!autoRunState.running) return;
    autoRunState.count += 1;
    const beforeY = window.scrollY;
    const beforeHeight = Math.max(document.documentElement.scrollHeight, document.body.scrollHeight);
    if (autoRunState.mode === 'scroll' || autoRunState.mode === 'both') {
      window.scrollBy({ top: Math.max(window.innerHeight * 0.82, 520), behavior: 'smooth' });
      autoRunState.message = '已自动下滑';
    }
    const nearBottom = beforeY + window.innerHeight >= beforeHeight - 120;
    if (autoRunState.mode === 'next' || (autoRunState.mode === 'both' && nearBottom)) {
      setTimeout(clickNextIfPossible, autoRunState.mode === 'both' ? 420 : 0);
    }
    autoRunState.lastHeight = beforeHeight;
    autoRunState.lastUrl = location.href;
    if (autoRunState.count >= autoRunState.max) stopAutoRun('已达到自动触发次数上限');
  }
  function startAutoRun(options = {}) {
    stopAutoRun();
    autoRunMissingSince = 0;
    const storedSelector = getStoredNextSelector();
    autoRunState = { running: true, count: 0, max: Math.min(Math.max(Number(options.max || 20), 1), 200), mode: options.mode || 'scroll', interval: Math.min(Math.max(Number(options.interval || 2500), 800), 20000), lastHeight: 0, lastUrl: location.href, status: 'running', message: '', selectedNextSelector: options.nextSelector || storedSelector };
    autoRunStep();
    autoRunTimer = setInterval(autoRunStep, autoRunState.interval);
    return getAutoRunState();
  }
  function getAutoRunState() { return { ...autoRunState, selectedNextSelector: autoRunState.selectedNextSelector || getStoredNextSelector() }; }
  function startPickNextButton() {
    const old = document.getElementById('__web_capture_pick_overlay__');
    if (old) old.remove();
    let current = null;
    const tip = document.createElement('div');
    tip.id = '__web_capture_pick_overlay__';
    tip.textContent = '请选择页面里的“下一页/翻页”按钮，Esc 取消';
    tip.style.cssText = 'position:fixed;left:50%;top:18px;transform:translateX(-50%);z-index:2147483647;background:#2563eb;color:#fff;padding:10px 14px;border-radius:12px;font:13px -apple-system,BlinkMacSystemFont,Segoe UI,Arial;box-shadow:0 12px 32px rgba(0,0,0,.2);pointer-events:none';
    const box = document.createElement('div');
    box.style.cssText = 'position:fixed;z-index:2147483646;border:2px solid #2563eb;background:rgba(37,99,235,.12);border-radius:8px;pointer-events:none;display:none';
    document.documentElement.appendChild(tip); document.documentElement.appendChild(box);
    const cleanup = () => { document.removeEventListener('mousemove', move, true); document.removeEventListener('click', click, true); document.removeEventListener('keydown', key, true); tip.remove(); box.remove(); };
    const move = (e) => { current = e.target?.closest?.('button,a,[role="button"],li,span') || e.target; if (!current || current === tip || current === box) return; const r = current.getBoundingClientRect(); box.style.display = 'block'; box.style.left = `${r.left}px`; box.style.top = `${r.top}px`; box.style.width = `${r.width}px`; box.style.height = `${r.height}px`; };
    const click = (e) => { e.preventDefault(); e.stopPropagation(); const el = current || e.target; const selector = cssPath(el); setStoredNextSelector(selector); autoRunState.selectedNextSelector = selector; autoRunState.message = `已选择翻页按钮：${selector}`; cleanup(); };
    const key = (e) => { if (e.key === 'Escape') { autoRunState.message = '已取消选择翻页按钮'; cleanup(); } };
    document.addEventListener('mousemove', move, true); document.addEventListener('click', click, true); document.addEventListener('keydown', key, true);
    return getAutoRunState();
  }

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    const action = message?.action || message?.type;
    if (action === 'startAutoRun') { sendResponse({ ok: true, state: startAutoRun(message?.options || {}) }); return true; }
    if (action === 'pickNextButton') { sendResponse({ ok: true, state: startPickNextButton() }); return true; }
    if (action === 'stopAutoRun') { sendResponse({ ok: true, state: stopAutoRun() }); return true; }
    if (action === 'getAutoRunState') { sendResponse({ ok: true, state: getAutoRunState() }); return true; }
    if (!['startRecording','stopRecording','getCapturedRequests','clearCapturedRequests','getRecordingState','getData','clearData'].includes(action)) return;
    const pageAction = action === 'getCapturedRequests' || action === 'getData' || action === 'getRecordingState' ? 'getRequests' : action === 'clearCapturedRequests' || action === 'clearData' ? 'clearRequests' : action;
    injectHook().then(() => askPage(pageAction, { rules: message?.rules || [] })).then((payload) => {
      const state = payload?.state || payload || {};
      const requests = payload?.requests || [];
      const last = requests.length ? requests[requests.length - 1] : null;
      if (last) state.lastUrl = last.url;
      if (action === 'getRecordingState') state.requests = requests;
      if (action === 'getCapturedRequests' || action === 'getData') sendResponse({ pageUrl: location.href, url: location.href, pageTitle: document.title, title: document.title, htmlContent: document.documentElement.outerHTML, xhrList: requests, startedAt: state.startedAt, endedAt: state.endedAt, captureTime: new Date().toISOString(), state });
      else sendResponse({ ok: true, state });
    });
    return true;
  });
})();
