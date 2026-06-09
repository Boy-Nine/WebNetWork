from __future__ import annotations

import json
import re
import shlex
from typing import Any
from urllib.parse import urlparse, parse_qsl

from fastapi import HTTPException

from .rule_engine import get_path


FIELD_LABEL_HINTS = {
    "nick": "店铺名称", "shop": "店铺", "shopname": "店铺名称", "shopinfo.title": "店铺名称",
    "item_id": "商品id", "itemid": "商品id", "id": "ID", "skuid": "skuId", "sku_id": "skuId",
    "realsales": "销量", "sales": "销量", "sold": "销量",
    "price": "价格", "priceshow.price": "券后价", "title": "商品标题", "name": "名称",
    "pic_path": "商品图片", "image": "图片", "img": "图片", "auctionurl": "商品链接", "url": "链接",
    "procity": "发货地", "userId": "用户ID", "userid": "用户ID", "leafcategory": "类目",
}


def normalize_key(value: str) -> str:
    return str(value or '').replace('_', '').replace('-', '').replace(' ', '').lower()


def guess_label(path: str) -> str:
    p = str(path)
    low = p.lower()
    if low in FIELD_LABEL_HINTS:
        return FIELD_LABEL_HINTS[low]
    normalized = normalize_key(p)
    if normalized in FIELD_LABEL_HINTS:
        return FIELD_LABEL_HINTS[normalized]
    tail = p.split('.')[-1]
    return FIELD_LABEL_HINTS.get(normalize_key(tail), tail)


def preview_value(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, (str, int, float, bool)):
        text = str(value)
    elif isinstance(value, list):
        text = f"Array({len(value)})"
    elif isinstance(value, dict):
        text = f"Object({len(value)})"
    else:
        text = str(value)
    return text[:160] + ('...' if len(text) > 160 else '')


def flatten_fields(obj: Any, prefix: str = '', depth: int = 0, limit: int = 300):
    out = []
    if len(out) >= limit or depth > 4:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, dict):
                out.extend(flatten_fields(v, path, depth + 1, limit))
            elif isinstance(v, list):
                if v and isinstance(v[0], dict):
                    out.extend(flatten_fields(v[0], f"{path}.0", depth + 1, limit))
                else:
                    out.append({"path": path, "label": guess_label(path), "value": preview_value(v), "type": "array"})
            else:
                out.append({"path": path, "label": guess_label(path), "value": preview_value(v), "type": type(v).__name__})
            if len(out) >= limit:
                break
    return out


VOLATILE_QUERY_KEYS = {
    "_", "t", "ts", "timestamp", "time", "sign", "signature", "callback", "jsonp", "cb",
    "uuid", "sid", "token", "loginType", "loginWQBiz", "g_ty", "g_tk", "sceneval", "h5st",
    "x-api-eid-token", "login_type", "loginwqbiz", "clientVersion", "client_version",
}
SENSITIVE_HEADER_KEYS = {"cookie", "authorization", "proxy-authorization", "x-csrf-token", "x-xsrf-token"}
DYNAMIC_PARAM_KEYS = {
    "page", "pageno", "pagenum", "page_num", "currentpage", "offset", "start", "limit", "size", "pagesize",
    "rn", "traceid", "requestid", "referer", "callback", "callbackname",
}
STABLE_PARAM_ALLOWLIST = {
    "appid", "app_id", "functionid", "function_id", "api", "method", "v", "version", "client", "type", "scene", "source", "channel",
}


def normalize_param_key(key: str) -> str:
    return str(key or '').strip().lower().replace('_', '').replace('-', '').replace('.', '')


def is_volatile_key(key: str) -> bool:
    low = str(key or '').strip().lower()
    normalized = normalize_param_key(low)
    volatile = {x.lower() for x in VOLATILE_QUERY_KEYS}
    volatile_normalized = {normalize_param_key(x) for x in volatile | DYNAMIC_PARAM_KEYS}
    return low in volatile or normalized in volatile_normalized or any(x in normalized for x in ("token", "sign", "timestamp"))


def looks_like_id_list(value: Any) -> bool:
    text = str(value or '').strip()
    if not text:
        return False
    if ',' in text and len([x for x in text.split(',') if x.strip()]) >= 3:
        return True
    return len(text) > 160 or bool(re.search(r'\d{10,}.*\d{10,}', text))


def is_stable_filter_value(key: str, value: Any) -> bool:
    if value in ('', None):
        return False
    nk = normalize_param_key(key)
    if nk in {normalize_param_key(x) for x in STABLE_PARAM_ALLOWLIST}:
        return True
    if isinstance(value, (dict, list)):
        return False
    text = str(value).strip()
    if looks_like_id_list(text):
        return False
    if text.startswith('{') or text.startswith('[') or text.startswith('http'):
        return False
    # 单纯很长的数字通常是商品/用户/时间戳，不适合做规则过滤。
    if re.fullmatch(r'\d{10,}', text):
        return False
    return len(text) <= 120


def stable_scalar_params(obj: Any, prefix: str = '', limit: int = 10) -> dict[str, Any]:
    """从 query/body 中挑选适合做规则过滤的稳定标量字段。"""
    out: dict[str, Any] = {}
    if not isinstance(obj, dict):
        return out
    # allowlist 优先，避免被普通业务字段挤掉 functionId/api。
    entries = list(obj.items())
    entries.sort(key=lambda kv: 0 if normalize_param_key(kv[0]) in {normalize_param_key(x) for x in STABLE_PARAM_ALLOWLIST} else 1)
    for k, v in entries:
        if len(out) >= limit:
            break
        key = str(k)
        path = f"{prefix}.{key}" if prefix else key
        if is_volatile_key(key):
            continue
        if isinstance(v, dict):
            for nk, nv in stable_scalar_params(v, path, limit - len(out)).items():
                out[nk] = nv
                if len(out) >= limit:
                    break
        elif isinstance(v, list):
            continue
        elif is_stable_filter_value(path, v):
            out[path] = v
    return out


def parse_curl_body(body_raw: str) -> tuple[Any | None, dict[str, Any]]:
    if not body_raw:
        return None, {}
    try:
        return json.loads(body_raw), {}
    except Exception:
        pass
    try:
        return None, dict(parse_qsl(body_raw, keep_blank_values=True))
    except Exception:
        return None, {}


def parse_curl_text(command: str) -> dict[str, Any]:
    # 兼容 macOS/Linux 反斜杠换行、PowerShell 反引号换行和浏览器 Copy as cURL 的普通换行。
    text = (command or '').replace("\\\n", ' ').replace('`\n', ' ').replace('\r', ' ').replace('\n', ' ').strip()
    if not text:
        raise HTTPException(status_code=400, detail="curl 文本不能为空")
    try:
        parts = shlex.split(text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"curl 解析失败：{exc}")
    if parts and parts[0].lower() in ('curl', 'curl.exe'):
        parts = parts[1:]
    method = ''
    headers: dict[str, str] = {}
    bodies: list[str] = []
    url = ''
    force_get_with_body = False
    warnings: list[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        nxt = parts[i + 1] if i + 1 < len(parts) else ''
        if part in ('-X', '--request') and nxt:
            method = nxt.upper(); i += 2; continue
        if part.startswith('-X') and len(part) > 2:
            method = part[2:].upper(); i += 1; continue
        if part in ('-I', '--head'):
            method = 'HEAD'; i += 1; continue
        if part in ('-G', '--get'):
            force_get_with_body = True; method = method or 'GET'; i += 1; continue
        if part in ('--url',) and nxt:
            url = nxt; i += 2; continue
        if part in ('-H', '--header') and nxt:
            if ':' in nxt:
                k, v = nxt.split(':', 1)
                key = k.strip()
                if key and key.lower() not in SENSITIVE_HEADER_KEYS:
                    headers[key] = v.strip()
            i += 2; continue
        if part in ('-b', '--cookie', '--user', '-u'):
            warnings.append(f"已忽略敏感参数 {part}")
            i += 2 if nxt else 1; continue
        if part in ('-d', '--data', '--data-raw', '--data-binary', '--data-ascii', '--data-urlencode') and nxt:
            bodies.append(nxt); i += 2; continue
        if part in ('--url-query',) and nxt:
            bodies.append(nxt); force_get_with_body = True; i += 2; continue
        if part.startswith('http://') or part.startswith('https://'):
            url = part
        i += 1
    if not url:
        raise HTTPException(status_code=400, detail="没有在 cURL 中找到 http/https URL")
    body_raw = '&'.join(bodies) if bodies else ''
    if force_get_with_body and body_raw:
        sep = '&' if '?' in url else '?'
        url = f"{url}{sep}{body_raw}"
        body_raw = ''
    parsed = urlparse(url)
    url_pattern = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    query_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    body_json, body_form = parse_curl_body(body_raw)
    stable_query = stable_scalar_params(query_params, limit=8)
    stable_body = stable_scalar_params(body_json if isinstance(body_json, dict) else body_form, limit=8)
    # GET 规则优先使用 query；POST/PUT/PATCH 优先 body，但保留少量 query 稳定参数用于接口族区分。
    if not method:
        method = 'POST' if body_raw else 'GET'
    params_filter = {**stable_query, **stable_body}
    params_filter = dict(list(params_filter.items())[:12])
    if any(is_volatile_key(k) for k in query_params.keys()) or body_raw:
        warnings.append("已自动忽略 timestamp/sign/callback/token/cookie 等易变化或敏感参数")
    if not params_filter:
        warnings.append("未发现稳定参数，当前规则主要依赖 URL 匹配；如接口过宽，建议手动补充 Params 过滤")
    host_name = parsed.netloc.replace('www.', '')
    return {
        "method": method,
        "url": url,
        "url_pattern": url_pattern,
        "url_match_type": "contains",
        "query_params": query_params,
        "params_filter": params_filter,
        "headers": headers,
        "body_raw": body_raw,
        "body_json": body_json,
        "body_form": body_form,
        "suggested_name": f"{host_name}{parsed.path}"[:80],
        "warnings": list(dict.fromkeys(warnings)),
    }


COMMON_LIST_KEYS = {"list", "items", "itemlist", "itemsarray", "goods", "products", "result", "data", "rows", "warelist", "auctions", "commentscount"}
FIELD_SPECS = [
    ("商品标题", ("title", "name", "warename", "skuname", "goodsname", "itemtitle", "productname"), None),
    ("商品id", ("itemid", "item_id", "wareid", "skuid", "sku_id", "productid", "id"), None),
    ("店铺名称", ("nick", "shopname", "shop_name", "shopinfo.title", "shop.title", "vendorname", "storename"), None),
    ("价格", ("priceshow.price", "price", "saleprice", "jdprice", "finalprice", "realprice", "pricedesc"), None),
    ("销量", ("realsales", "sales", "salecount", "commentcountstr", "goodcountstr", "sold", "paycount"), None),
    ("商品链接", ("auctionurl", "url", "link", "itemurl", "wareurl"), {"prefix": "https:"}),
    ("商品图片", ("pic_path", "image", "img", "picurl", "imageurl", "imgurl", "mainimage"), {"prefix": "https:"}),
]


def parse_params_for_rule(method: str, url: str, body_raw: str | None) -> dict[str, Any]:
    params = dict(parse_qsl(urlparse(url or '').query, keep_blank_values=True))
    # 京东/淘宝常把真正业务参数放在 query 的 body/data 里，规则生成时展开成 body.xxx。
    for embedded_key in ("body", "data", "payload", "param"):
        val = params.get(embedded_key)
        if isinstance(val, str):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, dict):
                    params[embedded_key] = parsed
            except Exception:
                pass
    if body_raw:
        body_json, body_form = parse_curl_body(body_raw)
        if isinstance(body_json, dict):
            params.update(body_json)
        elif body_form:
            params.update(body_form)
    return params


def find_arrays(obj: Any, path: str = '', depth: int = 0, out: list[dict[str, Any]] | None = None):
    if out is None:
        out = []
    if depth > 7 or obj is None:
        return out
    if isinstance(obj, list):
        dict_items = [x for x in obj if isinstance(x, dict)]
        if dict_items:
            sample = dict_items[0]
            score = len(dict_items) * 2 + len(sample)
            tail = path.split('.')[-1].lower().replace('_', '') if path else ''
            if tail in COMMON_LIST_KEYS:
                score += 20
            out.append({"path": path, "count": len(dict_items), "sample": sample, "score": score})
        for i, item in enumerate(obj[:3]):
            find_arrays(item, f"{path}.{i}" if path else str(i), depth + 1, out)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            find_arrays(v, f"{path}.{k}" if path else str(k), depth + 1, out)
    return out


def path_exists_in_sample(sample: dict[str, Any], path: str) -> bool:
    return get_path(sample, path) is not None


def normalized_path(path: str) -> str:
    return normalize_param_key(path).replace('0', '')


def semantic_score(label: str, path: str, value: Any, aliases: tuple[str, ...]) -> int:
    np = normalized_path(path)
    tail = normalized_path(path.split('.')[-1])
    score = 0
    for alias in aliases:
        na = normalized_path(alias)
        if np == na or tail == na:
            score = max(score, 100)
        elif np.endswith(na) or na in np:
            score = max(score, 75)
    text = str(value or '')
    if label == '商品标题' and isinstance(value, str) and len(text) >= 6 and not re.fullmatch(r'[\d.]+', text):
        score += 10
    if label == '价格' and re.search(r'\d+(\.\d+)?', text) and len(text) <= 30:
        score += 8
    if label == '商品链接' and ('url' in np or 'link' in np or text.startswith(('http', '//'))):
        score += 15
    if label == '商品图片' and ('img' in np or 'pic' in np or 'image' in np):
        score += 12
    return score


def best_field_for(sample: dict[str, Any], label: str, aliases: tuple[str, ...]):
    candidates = []
    for f in flatten_fields(sample, limit=200):
        path = str(f.get('path') or '')
        value = get_path(sample, path)
        score = semantic_score(label, path, value, aliases)
        if score > 0:
            candidates.append((score, path, value))
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0] if candidates else None


def platform_from_url(url: str) -> str:
    host = urlparse(url or '').netloc.lower()
    if 'jd.com' in host:
        return 'jd'
    if 'taobao.com' in host or 'tmall.com' in host or 'taobao' in (url or '').lower():
        return 'taobao'
    return 'generic'


def link_template_for(platform: str, id_path: str | None) -> dict[str, Any] | None:
    if not id_path:
        return None
    if platform == 'jd':
        return {"path": id_path, "template": "https://item.jd.com/{value}.html"}
    if platform == 'taobao':
        return {"path": id_path, "template": "https://item.taobao.com/item.htm?id={value}"}
    return None


def infer_mapping_from_sample(sample: dict[str, Any], api_url: str = '') -> tuple[dict[str, Any], list[dict[str, Any]]]:
    mapping: dict[str, Any] = {}
    matches: list[dict[str, Any]] = []
    used = set()
    id_path = None
    platform = platform_from_url(api_url)
    for label, aliases, transform_hint in FIELD_SPECS:
        best = best_field_for(sample, label, aliases)
        if not best:
            continue
        score, path, value = best
        if path in used:
            continue
        cfg: Any = path
        if label == "商品标题":
            cfg = {"path": path, "stripHtml": True}
        elif transform_hint:
            cfg = {"path": path, **transform_hint}
        mapping[label] = cfg
        used.add(path)
        matches.append({"label": label, "path": path, "score": score, "sample": preview_value(value)})
        if label == '商品id':
            id_path = path
    # 没有现成商品链接时，按平台和商品 ID 自动拼链接。
    if '商品链接' not in mapping:
        tpl = link_template_for(platform, id_path)
        if tpl:
            mapping['商品链接'] = tpl
            matches.append({"label": "商品链接", "path": id_path, "score": 88, "sample": tpl.get('template')})
    # 如果常用字段太少，再补几个标量字段；但避免把整堆无语义指标全塞进去。
    if len(mapping) < 3:
        fields = flatten_fields(sample, limit=80)
        for f in fields:
            path = f.get('path')
            if not path or path in used or '.0.' in path:
                continue
            value = get_path(sample, path)
            if isinstance(value, str) and len(value) > 200:
                continue
            mapping[f.get('label') or path] = path
            used.add(path)
            matches.append({"label": f.get('label') or path, "path": path, "score": 35, "sample": preview_value(value)})
            if len(mapping) >= 6:
                break
    return mapping, matches


def confidence_score(url_pattern: str, params_filter: dict[str, Any], best: dict[str, Any] | None, mapping: dict[str, Any]) -> int:
    score = 20 if url_pattern else 0
    score += min(len(params_filter), 4) * 8
    if best:
        score += 28
        if best.get('count', 0) >= 5:
            score += 8
    semantic_fields = {'商品标题', '商品id', '店铺名称', '价格', '销量', '商品链接', '商品图片'}
    score += min(len(set(mapping) & semantic_fields), 5) * 8
    return max(0, min(score, 100))


def suggest_rule_from_api(api: Any) -> dict[str, Any]:
    parsed = urlparse(api.url or '')
    url_pattern = f"{parsed.scheme}://{parsed.netloc}{parsed.path}" if parsed.scheme and parsed.netloc else (api.url or '')
    params_filter = stable_scalar_params(parse_params_for_rule(api.method or 'GET', api.url or '', api.request_body_raw), limit=8)
    arrays = sorted(find_arrays(api.response_body), key=lambda x: x.get('score', 0), reverse=True)
    best = arrays[0] if arrays else None
    sample = best.get('sample') if best else (api.response_body if isinstance(api.response_body, dict) else {})
    mapping, mapping_matches = infer_mapping_from_sample(sample, api.url or '') if isinstance(sample, dict) else ({}, [])
    host_name = (parsed.netloc or '接口').replace('www.', '')
    warnings = []
    if not best:
        warnings.append("没有在响应中识别到列表数组，已按响应根对象生成字段映射")
    if not mapping:
        warnings.append("没有识别到高价值商品字段，建议手动选择字段")
    if not params_filter:
        warnings.append("未发现稳定 Params，规则会主要依赖 URL 匹配")
    confidence = confidence_score(url_pattern, params_filter, best, mapping)
    return {
        "name": f"{host_name}{parsed.path or ''}"[:80],
        "method": api.method,
        "url_pattern": url_pattern,
        "url_match_type": "contains",
        "params_filter": params_filter,
        "response_list_path": best.get('path') if best else '',
        "field_mapping": mapping,
        "confidence": confidence,
        "confidence_label": "高" if confidence >= 80 else "中" if confidence >= 55 else "低",
        "mapping_matches": mapping_matches,
        "sample": {
            "api_id": api.id,
            "api_url": api.url,
            "list_count": best.get('count') if best else 0,
            "list_candidates": [{"path": x.get('path'), "count": x.get('count'), "score": x.get('score')} for x in arrays[:8]],
            "sample_item": sample,
        },
        "warnings": warnings,
    }
