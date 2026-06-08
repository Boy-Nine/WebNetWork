from __future__ import annotations
import re
from html import unescape
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode, quote
from typing import Any
from .api_parser import parse_json_or_text, parse_form, parse_query, find_search_keyword

CHANNEL_COLUMNS = {
    "platform_user", "source_user_id", "platform", "source_created_at", "search_keyword", "channel_title",
    "channel_url", "sku_id", "price", "sales", "channel_image", "shop_name", "shop_id", "shop_url",
    "ad_tag", "product_activity", "discount_strength", "platform_category", "product_info", "ranking_info",
    "ship_from", "product_marketing", "shop_marketing", "article_number", "serial_number", "core_tags",
    "activity_source", "channel_page_title", "shop_tags",
}

# 用户在规则里常用中文字段名，这里映射到固定渠道商品表字段。
# 动态标签表 label_data_records 不会强制转换，会按用户配置的展示字段原样落 row_data。
DISPLAY_TO_CHANNEL_COLUMN = {
    "店铺名称": "shop_name",
    "店铺": "shop_name",
    "商品id": "sku_id",
    "商品ID": "sku_id",
    "item_id": "sku_id",
    "sku_id": "sku_id",
    "SKU": "sku_id",
    "销量": "sales",
    "付款人数": "sales",
    "价格": "price",
    "商品名": "channel_title",
    "商品标题": "channel_title",
    "标题": "channel_title",
    "商品链接": "channel_url",
    "链接": "channel_url",
    "图片": "channel_image",
    "渠道图片": "channel_image",
    "搜索词": "search_keyword",
}

def get_path(obj: Any, path: str | None):
    if not path:
        return obj
    cur = obj
    for part in path.split('.'):
        if part == '':
            continue
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except Exception:
                return None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur

def stringify(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return ','.join([stringify(v) or '' for v in value if v is not None]) or None
    return None



def strip_html_text(value: str) -> str:
    return re.sub(r'<[^>]+>', '', unescape(value or '')).strip()

def remove_query_params(value: str, remove_keys: list[str] | tuple[str, ...] | set[str] | None = None, keep_keys: list[str] | tuple[str, ...] | set[str] | None = None) -> str:
    if not value or ('?' not in value and not keep_keys):
        return value
    try:
        parts = urlsplit(value)
        remove = {str(x) for x in (remove_keys or [])}
        keep = {str(x) for x in (keep_keys or [])}
        pairs = parse_qsl(parts.query, keep_blank_values=True)
        if keep:
            pairs = [(k, v) for k, v in pairs if k in keep]
        if remove:
            pairs = [(k, v) for k, v in pairs if k not in remove]
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(pairs, doseq=True), parts.fragment))
    except Exception:
        return value

def field_hint(cfg: dict[str, Any]) -> str:
    return (str(cfg.get('__display_field') or cfg.get('label') or cfg.get('field') or cfg.get('name') or '') + ' ' + str(cfg.get('__source_path') or cfg.get('path') or cfg.get('source') or '')).lower()

def looks_like_url_field(cfg: dict[str, Any], value: Any) -> bool:
    text = stringify(value) or ''
    keys = field_hint(cfg)
    return text.startswith('//') or any(x in keys for x in ('url', 'link', '链接', '图片', 'pic', 'image'))

def looks_like_title_field(cfg: dict[str, Any]) -> bool:
    keys = field_hint(cfg)
    return any(x in keys for x in ('title', '标题', '商品名', '商品名称'))

def normalize_protocol_relative_url(text: str) -> str:
    return 'https:' + text if isinstance(text, str) and text.startswith('//') else text

def render_template(template: str, value: Any, item: Any = None, *, url_encode: bool = False) -> str:
    def fmt(v: Any) -> str:
        text = stringify(v) or ''
        return quote(text, safe='') if url_encode else text
    def replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        if key in ('value', '.', 'this'):
            return fmt(value)
        return fmt(get_path(item, key))
    return re.sub(r'\{\s*([^{}]+?)\s*\}', replace, str(template))

def apply_value_transform(value: Any, transform: dict[str, Any] | None = None, item: Any = None) -> str | None:
    cfg = transform if isinstance(transform, dict) else {}
    template = cfg.get('template') or cfg.get('format') or cfg.get('tpl')
    text = stringify(value)
    if text is None and not template:
        return None
    if text is None:
        text = ''
    if template:
        text = render_template(str(template), text, item, url_encode=bool(cfg.get('urlEncode') or cfg.get('url_encode')))
    if looks_like_url_field(cfg, value) or looks_like_url_field(cfg, text):
        text = normalize_protocol_relative_url(text)
    if looks_like_title_field(cfg):
        text = strip_html_text(text)
    if cfg.get('stripHtml') or cfg.get('strip_html') or cfg.get('removeHtml'):
        text = strip_html_text(text)
    if cfg.get('decodeUri') or cfg.get('decode_uri'):
        try:
            from urllib.parse import unquote
            text = unquote(text)
        except Exception:
            pass
    for key in ('removePrefix', 'remove_prefix'):
        prefix = cfg.get(key)
        if prefix and text.startswith(str(prefix)):
            text = text[len(str(prefix)):]
    for key in ('removeSuffix', 'remove_suffix'):
        suffix = cfg.get(key)
        if suffix and text.endswith(str(suffix)):
            text = text[:-len(str(suffix))]
    if cfg.get('cutBefore') or cfg.get('cut_before'):
        marker = str(cfg.get('cutBefore') or cfg.get('cut_before'))
        if marker in text:
            text = text.split(marker, 1)[1]
    if cfg.get('cutAfter') or cfg.get('cut_after'):
        marker = str(cfg.get('cutAfter') or cfg.get('cut_after'))
        if marker in text:
            text = text.split(marker, 1)[0]
    replacements = cfg.get('replace') or cfg.get('replaces') or []
    if isinstance(replacements, dict):
        replacements = list(replacements.items())
    for item in replacements if isinstance(replacements, list) else []:
        try:
            old, new = (item if isinstance(item, (list, tuple)) else (item.get('from'), item.get('to')))
            text = text.replace(str(old), str(new or ''))
        except Exception:
            continue
    regex_replacements = cfg.get('regexReplace') or cfg.get('regex_replace') or []
    if isinstance(regex_replacements, dict):
        regex_replacements = [regex_replacements]
    for item in regex_replacements if isinstance(regex_replacements, list) else []:
        try:
            text = re.sub(str(item.get('pattern', '')), str(item.get('replace', '')), text)
        except Exception:
            continue
    # 先补前缀再删 query，方便 //item.taobao.com 被转成 https://item.taobao.com 后标准化。
    prefix = cfg.get('prefix')
    if prefix:
        prefix = str(prefix)
        if prefix == 'https:' and text.startswith('//'):
            text = 'https:' + text
        elif prefix == 'http:' and text.startswith('//'):
            text = 'http:' + text
        elif not text.startswith(prefix):
            text = prefix + text
    suffix = cfg.get('suffix')
    if suffix and not text.endswith(str(suffix)):
        text = text + str(suffix)
    remove_query = cfg.get('removeQuery') or cfg.get('remove_query') or cfg.get('dropQuery') or cfg.get('drop_query')
    keep_query = cfg.get('keepQuery') or cfg.get('keep_query')
    if remove_query or keep_query:
        text = remove_query_params(text, remove_query, keep_query)
    if cfg.get('trim', True):
        text = text.strip()
    max_len = cfg.get('maxLength') or cfg.get('max_length')
    if max_len:
        try:
            text = text[:int(max_len)]
        except Exception:
            pass
    return text

def normalize_field_specs(rows: list[dict[str, Any]], mapping: dict[str, Any]):
    """把旧/新字段规则统一为 (display_field, source_path, transform)。

    支持旧写法：
      {"nick": "店铺名称"} 或 {"店铺名称": "nick"}
    支持新写法：
      {"auctionURL": {"label":"商品链接", "prefix":"https:", "removeQuery":["mi_id"]}}
      {"商品链接": {"path":"auctionURL", "prefix":"https:"}}
    """
    specs = []
    for left, right in (mapping or {}).items():
        left_s = str(left)
        if isinstance(right, dict):
            cfg = dict(right)
            source_path = str(cfg.pop('path', '') or cfg.pop('source', '') or cfg.pop('sourcePath', '') or cfg.pop('source_path', '') or '')
            if not source_path and (cfg.get('template') or cfg.get('format') or cfg.get('tpl')):
                source_path = '.'
            label = str(cfg.pop('label', '') or cfg.pop('field', '') or cfg.pop('name', '') or '')
            left_exists = any(path_exists(item, left_s) for item in rows)
            if not source_path:
                source_path = left_s if left_exists else str(right.get('value', '') or '')
            if not label:
                label = left_s if not left_exists else source_path
                if left_exists:
                    label = left_s
            # 如果 key 是源路径且 label 缺失，用 key 作为路径时 label 仍可由外层或 path 推断。
            if left_exists and not (right.get('path') or right.get('source') or right.get('sourcePath') or right.get('source_path')):
                label = str(right.get('label') or right.get('field') or right.get('name') or left_s)
                source_path = left_s
            cfg['__display_field'] = label
            cfg['__source_path'] = source_path
            specs.append((label, source_path, cfg))
            continue
        left_exists = any(path_exists(item, left_s) for item in rows)
        right_s = str(right)
        right_exists = any(path_exists(item, right_s) for item in rows)
        if left_exists and not right_exists:
            specs.append((right_s, left_s, {'__display_field': right_s, '__source_path': left_s}))
        else:
            specs.append((left_s, right_s, {'__display_field': left_s, '__source_path': right_s}))
    return specs

def path_exists(obj: Any, path: str | None) -> bool:
    if not path:
        return obj is not None
    sentinel = object()
    cur = obj
    for part in str(path).split('.'):
        if part == '':
            continue
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except Exception:
                return False
        elif isinstance(cur, dict):
            cur = cur.get(part, sentinel)
            if cur is sentinel:
                return False
        else:
            return False
    return cur is not None

def infer_field_mapping(rows: list[dict[str, Any]], mapping: dict[str, Any]):
    # 兼容两种规则写法，并且按整批 rows 判断方向，避免某一行缺字段时方向摇摆。
    # 1) {"接口字段路径": "落表/展示字段名"}，如 {"nick": "店铺名称"}
    # 2) {"落表/展示字段名": "接口字段路径"}，如 {"店铺名称": "nick"}
    pairs = []
    for left, right in mapping.items():
        left_s, right_s = str(left), str(right)
        left_exists = any(path_exists(item, left_s) for item in rows)
        right_exists = any(path_exists(item, right_s) for item in rows)
        if left_exists and not right_exists:
            pairs.append((right_s, left_s))
        else:
            # 保持旧版兼容：默认 key 是目标字段，value 是源路径。
            pairs.append((left_s, right_s))
    return pairs

def channel_column_for(display_field: str) -> str | None:
    return DISPLAY_TO_CHANNEL_COLUMN.get(display_field) or (display_field if display_field in CHANNEL_COLUMNS else None)

def match_url(url: str, pattern: str, match_type: str = 'contains') -> bool:
    pattern = str(pattern or '').strip()
    url = str(url or '').strip()
    if not pattern:
        return False
    if match_type == 'regex':
        try:
            return re.search(pattern, url) is not None
        except re.error:
            return False
    if match_type == 'equals':
        return url == pattern
    return pattern in url

def coerce_nested_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return value
    try:
        import json
        if (text.startswith('{') and text.endswith('}')) or (text.startswith('[') and text.endswith(']')):
            return json.loads(text)
    except Exception:
        return value
    return value

def get_deep_param(params: Any, path: str):
    cur = params
    for part in str(path or '').split('.'):
        if part == '':
            continue
        cur = coerce_nested_value(cur)
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except Exception:
                return None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur

def params_match(request_params: Any, params_filter: Any) -> bool:
    if not params_filter:
        return True
    if not isinstance(params_filter, dict):
        return True
    if not isinstance(request_params, dict):
        return False
    for k, expected in params_filter.items():
        actual = get_deep_param(request_params, str(k))
        if actual is None:
            return False
        if expected in (None, ''):
            continue
        if str(expected) not in str(actual):
            return False
    return True

def find_matching_rule(api_data: dict, rules: list[Any]):
    for rule in rules:
        if not getattr(rule, 'enabled', 1):
            continue
        if rule.method and rule.method.upper() != api_data.get('method'):
            continue
        if not match_url(api_data.get('url') or '', rule.url_pattern, rule.url_match_type):
            continue
        if not params_match(api_data.get('request_params'), rule.params_filter):
            continue
        return rule
    return None

def parse_by_rule(response_body: Any, rule: Any, fallback_search_keyword: str | None = None) -> list[dict[str, Any]]:
    if not rule:
        return []
    root = get_path(response_body, getattr(rule, 'response_list_path', None))
    if isinstance(root, dict):
        rows = [root]
    elif isinstance(root, list):
        rows = [x for x in root if isinstance(x, dict)]
    else:
        rows = []
    mapping = getattr(rule, 'field_mapping', None) or {}
    if not isinstance(mapping, dict):
        mapping = {}
    out = []
    field_specs = normalize_field_specs(rows, mapping)
    for item in rows:
        mapped = {col: None for col in CHANNEL_COLUMNS}
        for display_field, source_path, transform in field_specs:
            if not display_field or not source_path:
                continue
            target = channel_column_for(str(display_field))
            if not target:
                continue
            mapped[target] = apply_value_transform(get_path(item, str(source_path)), transform, item)
        if not mapped.get('search_keyword') and fallback_search_keyword:
            mapped['search_keyword'] = fallback_search_keyword
        mapped['raw_item'] = item
        # 规则解析允许字段很少，但至少要有一个映射字段命中，避免空行。
        if any(v for k, v in mapped.items() if k != 'raw_item'):
            out.append(mapped)
    return out

def parse_dynamic_rows_by_rule(response_body: Any, rule: Any, fallback_search_keyword: str | None = None) -> list[dict[str, Any]]:
    """按规则 field_mapping 生成动态字段行。

    与 channel_product_records 的固定字段不同，这里 row_data 的字段名完全来自
    field_mapping 的 key：用户在 WebPC 配了什么字段，标签明细表就展示什么字段。
    """
    if not rule:
        return []
    root = get_path(response_body, getattr(rule, 'response_list_path', None))
    if isinstance(root, dict):
        rows = [root]
    elif isinstance(root, list):
        rows = [x for x in root if isinstance(x, dict)]
    else:
        rows = []
    mapping = getattr(rule, 'field_mapping', None) or {}
    if not isinstance(mapping, dict):
        mapping = {}
    out = []
    field_specs = normalize_field_specs(rows, mapping)
    for item in rows:
        row_data = {}
        for display_field, source_path, transform in field_specs:
            if not display_field or not source_path:
                continue
            row_data[str(display_field)] = apply_value_transform(get_path(item, str(source_path)), transform, item)
        if fallback_search_keyword and "搜索词" not in row_data and "search_keyword" not in row_data:
            row_data["搜索词"] = fallback_search_keyword
        # 如果除了搜索词以外没有任何有效字段，不落标签明细表，避免空商品行污染数据。
        non_search_values = [v for k, v in row_data.items() if str(k) not in ("搜索词", "search_keyword")]
        if any(v not in (None, "") for v in non_search_values):
            out.append({"row_data": row_data, "raw_item": item})
    return out
