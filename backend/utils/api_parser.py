from __future__ import annotations
import json
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse, unquote_plus

SENSITIVE_KEYS = {"password", "passwd", "pwd", "token", "access_token", "refresh_token", "authorization", "cookie", "set-cookie", "secret", "apikey", "api_key"}
SEARCH_KEYS = {"keyword", "keywords", "search", "searchword", "search_word", "searchkeyword", "search_keyword", "query", "q", "wd", "key", "term", "word", "text"}

def mask_sensitive(value):
    if isinstance(value, dict):
        return {k: ("******" if str(k).lower() in SENSITIVE_KEYS else mask_sensitive(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [mask_sensitive(v) for v in value]
    return value

def body_size(value: str | None) -> int | None:
    return len(value.encode("utf-8")) if isinstance(value, str) else None

def first_content_type(headers: dict | None) -> str | None:
    if not headers:
        return None
    for k, v in headers.items():
        if str(k).lower() == "content-type":
            return str(v)
    return None




def first_present(item: dict, *keys):
    for key in keys:
        if key in item and item.get(key) is not None:
            return item.get(key)
    return None

def normalize_headers(value):
    if not value:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        out = {}
        for pair in value:
            try:
                k, v = pair
                out[str(k)] = v
            except Exception:
                continue
        return out or None
    if isinstance(value, str):
        out = {}
        for line in value.strip().splitlines():
            if ':' not in line:
                continue
            k, v = line.split(':', 1)
            k = k.strip()
            if k:
                out[k] = v.strip()
        return out or None
    return None

def truncate_text(value, max_bytes: int) -> str | None:
    if value is None:
        return None
    text = value if isinstance(value, str) else str(value)
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return text
    return raw[:max_bytes].decode("utf-8", errors="ignore") + "\n...[truncated]"


def parse_json_or_text(raw: str | None):
    """尝试把请求/响应原始字符串解析为 JSON。

    兼容淘宝/MTOP 常见 JSONP：mtopjsonp16({...})，否则返回 (None, 原文)。
    """
    if raw is None or raw == "":
        return None, raw
    text = raw.strip() if isinstance(raw, str) else str(raw).strip()
    candidates = [text]
    # 通用 JSONP：mtopjsonp16({...})、jsonp123([...])、window.foo.bar({...}) 等，回调名不固定。
    m = re.match(r"^(?:window\.)?[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*\s*\((.*)\)\s*;?\s*$", text, re.S)
    if m:
        candidates.append(m.group(1).strip())
    # 兜底：有些响应前后会混入注释/防劫持前缀，尝试提取最外层 JSON 对象或数组。
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        first, last = text.find(open_ch), text.rfind(close_ch)
        if first >= 0 and last > first:
            candidates.append(text[first:last + 1])
    for candidate in candidates:
        try:
            return json.loads(candidate), raw
        except Exception:
            continue
    return None, raw


def parse_query(url: str) -> dict:
    parsed = urlparse(url or "")
    qs = parse_qs(parsed.query, keep_blank_values=True)
    return mask_sensitive({k: v[0] if len(v) == 1 else v for k, v in qs.items()})


def safe_decode_text(value):
    if value is None:
        return None
    text = str(value)
    try:
        return unquote_plus(text)
    except Exception:
        return text


def normalize_key(key: str) -> str:
    return str(key or "").replace("_", "").replace("-", "").replace(" ", "").lower()


NORMALIZED_SEARCH_KEYS = {normalize_key(x) for x in SEARCH_KEYS}

def parse_embedded_value(value: str):
    """解析接口里常见的嵌套字符串：URL 编码 JSON、JSON 字符串、querystring。"""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    variants = [text]
    try:
        decoded = unquote_plus(text)
        if decoded != text:
            variants.append(decoded)
    except Exception:
        pass
    for candidate in variants:
        c = candidate.strip()
        if not c:
            continue
        if (c.startswith('{') and c.endswith('}')) or (c.startswith('[') and c.endswith(']')):
            try:
                return json.loads(c)
            except Exception:
                pass
        if '=' in c and '&' in c:
            parsed = parse_form(c)
            if parsed:
                return parsed
    return None

def find_search_keyword(value, depth: int = 0) -> str | None:
    if value is None or depth > 6:
        return None
    if isinstance(value, str):
        nested = parse_embedded_value(value)
        if nested is not None and nested is not value:
            return find_search_keyword(nested, depth + 1)
        return None
    if isinstance(value, dict):
        for k, v in value.items():
            if normalize_key(k) in NORMALIZED_SEARCH_KEYS and not isinstance(v, (dict, list)) and v not in (None, ""):
                return str(v)
        for v in value.values():
            found = find_search_keyword(v, depth + 1)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = find_search_keyword(item, depth + 1)
            if found:
                return found
    return None


def extract_search_keyword(url: str, request_body_raw: str | None, request_params=None, explicit: str | None = None) -> str | None:
    if explicit:
        return safe_decode_text(explicit)[:500]
    query = parse_query(url)
    found = find_search_keyword(query)
    if found:
        return safe_decode_text(found)[:500]
    found = find_search_keyword(request_params)
    if found:
        return safe_decode_text(found)[:500]
    parsed_json, _ = parse_json_or_text(request_body_raw)
    found = find_search_keyword(parsed_json)
    if found:
        return safe_decode_text(found)[:500]
    form = parse_form(request_body_raw)
    found = find_search_keyword(form)
    return safe_decode_text(found)[:500] if found else None


def parse_form(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        qs = parse_qs(raw, keep_blank_values=True)
        return mask_sensitive({k: v[0] if len(v) == 1 else v for k, v in qs.items()})
    except Exception:
        return None


def parse_request_params(method: str, url: str, request_body_raw: str | None):
    """解析请求参数：GET 优先 query；其他方法优先 JSON body，再尝试表单，最后保留 raw。"""
    query = parse_query(url)
    if method.upper() == "GET":
        return query or None
    parsed_json, _ = parse_json_or_text(request_body_raw)
    if parsed_json is not None:
        return mask_sensitive(parsed_json)
    form = parse_form(request_body_raw)
    if form:
        return mask_sensitive(form)
    if query:
        return mask_sensitive({"query": query, "rawBody": request_body_raw}) if request_body_raw else query
    return mask_sensitive({"raw": request_body_raw}) if request_body_raw else None


def normalize_dt(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # 插件 timestamp 可能是毫秒级 Date.now()，也兼容秒级时间戳。
        return datetime.fromtimestamp(value / 1000 if value > 10_000_000_000 else value, tz=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except Exception:
            return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return None


def build_parsed_api(item: dict, *, user_id: int, session_id: int, page_url: str, page_title: str | None, fallback_time: datetime, max_body_bytes: int) -> dict:
    method = (item.get("method") or "GET").upper()[:12]
    url = item.get("url") or ""
    request_body_raw = truncate_text(first_present(item, "requestBody", "request_body", "request_body_raw", "body", "postData"), max_body_bytes)
    response_body_raw = truncate_text(first_present(item, "responseBody", "response_body", "response_body_raw", "responseText", "response"), max_body_bytes)
    response_json, response_text = parse_json_or_text(response_body_raw)
    response_status = first_present(item, "responseStatus", "response_status", "status", "statusCode")
    try:
        response_status = int(response_status) if response_status is not None else None
    except Exception:
        response_status = None
    duration = first_present(item, "duration", "durationMs", "duration_ms", "elapsed")
    try:
        duration = int(duration) if duration is not None else None
    except Exception:
        duration = None
    captured_at = normalize_dt(item.get("timestamp")) or fallback_time
    parsed_url = urlparse(url or "")
    req_headers = normalize_headers(first_present(item, "requestHeaders", "request_headers", "headers", "requestHeader"))
    resp_headers = normalize_headers(first_present(item, "responseHeaders", "response_headers", "responseHeader"))
    content_type = first_content_type(resp_headers) or first_content_type(req_headers)
    query_params = parse_query(url)
    request_params = parse_request_params(method, url, request_body_raw)
    search_keyword = extract_search_keyword(url, request_body_raw, request_params, item.get("searchKeyword"))
    return {
        "user_id": user_id,
        "session_id": session_id,
        "method": method,
        "url": url,
        "request_headers": req_headers if req_headers else None,
        "response_headers": resp_headers if resp_headers else None,
        "request_params": request_params,
        "query_params": query_params or None,
        "search_keyword": search_keyword,
        "host": parsed_url.netloc or None,
        "path": parsed_url.path or None,
        "content_type": content_type,
        "is_json": 1 if response_json is not None or "json" in str(content_type or "").lower() else 0,
        "response_size": body_size(response_body_raw),
        "request_body_raw": request_body_raw,
        "response_status": response_status,
        "response_body": response_json,
        "response_body_text": response_text if response_json is None else None,
        "response_body_raw": response_body_raw,
        "duration_ms": duration,
        "page_url": page_url,
        "page_title": page_title,
        "captured_at": captured_at,
    }
