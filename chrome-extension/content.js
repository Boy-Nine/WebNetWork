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
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    const action = message?.action || message?.type;
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
