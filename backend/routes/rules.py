from __future__ import annotations
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import CaptureRule, DataLabel, User, UserRuleSelection, ParsedApi
from ..utils.security import get_current_user, mask_phone
from ..utils.api_parser import parse_json_or_text
from ..utils.rule_engine import get_path, match_url, params_match, parse_dynamic_rows_by_rule, normalize_field_specs, apply_value_transform
from ..utils.rule_suggester import parse_curl_text, suggest_rule_from_api, flatten_fields, preview_value, find_arrays
from ..utils.membership import require_capacity, require_feature

router = APIRouter(prefix="/api/rules", tags=["capture rules"])


def find_sample_item(response_body: Any, response_list_path: str | None):
    root = get_path(response_body, response_list_path) if response_list_path else response_body
    if isinstance(root, list):
        return next((x for x in root if isinstance(x, dict)), None), len(root)
    if isinstance(root, dict):
        return root, 1
    return None, 0

class RuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    enabled: int = 1
    label_id: int | None = None
    method: str | None = None
    url_pattern: str = Field(min_length=1)
    url_match_type: str = "contains"
    params_filter: dict[str, Any] | None = None
    response_list_path: str | None = None
    field_mapping: dict[str, Any] | None = None
    remark: str | None = None

class CurlParseIn(BaseModel):
    curl: str = Field(min_length=1, max_length=50000)

class ResponseFieldsIn(BaseModel):
    response: str = Field(min_length=1, max_length=2_000_000)
    response_list_path: str | None = None


def normalize_rule_payload(data: dict[str, Any]) -> dict[str, Any]:
    # 用户输入的 URL/路径常会复制出前后空格；保存前统一清理，避免插件匹配失败。
    for key in ("name", "method", "url_pattern", "url_match_type", "response_list_path", "remark"):
        if isinstance(data.get(key), str):
            data[key] = data[key].strip()
    if data.get("method"):
        data["method"] = str(data["method"]).upper()
    return data


def out(rule: CaptureRule):
    return {
        "id": rule.id,
        "creator_user_id": rule.user_id,
        "creator_phone": mask_phone(rule.creator_phone),
        "can_edit": False,
        "selected": False,
        "name": rule.name,
        "enabled": rule.enabled,
        "label_id": rule.label_id,
        "label_name": rule.label_name,
        "method": rule.method,
        "url_pattern": rule.url_pattern,
        "url_match_type": rule.url_match_type,
        "params_filter": rule.params_filter,
        "response_list_path": rule.response_list_path,
        "field_mapping": rule.field_mapping,
        "remark": rule.remark,
        "created_at": rule.created_at,
    }

def out_for_user(rule: CaptureRule, user: User):
    data = out(rule)
    data["can_edit"] = rule.user_id == user.id
    return data

@router.get("/list")
def list_rules(enabledOnly: bool = False, selectedOnly: bool = False, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # 规则公共可读：所有登录用户都能看到公共规则；插件只加载当前用户已勾选的规则。
    q = db.query(CaptureRule)
    if enabledOnly:
        q = q.filter(CaptureRule.enabled == 1)
    selected_ids = {x.rule_id for x in db.query(UserRuleSelection).filter(UserRuleSelection.user_id == user.id).all()}
    if selectedOnly:
        if not selected_ids:
            return {"code": 0, "data": []}
        q = q.filter(CaptureRule.id.in_(selected_ids))
    rows = q.order_by(CaptureRule.created_at.desc(), CaptureRule.id.desc()).all()
    data = []
    for r in rows:
        item = out_for_user(r, user)
        item["selected"] = r.id in selected_ids
        data.append(item)
    return {"code": 0, "data": data}


@router.post("/parse-curl")
def parse_curl(payload: CurlParseIn, user: User = Depends(get_current_user)):
    require_feature(user, "curl_import")
    # 安全说明：只解析 cURL 文本，不执行命令，也不会请求目标 URL。
    return {"code": 0, "data": parse_curl_text(payload.curl)}



@router.get("/suggest-from-api/{api_id}")
def suggest_from_api(api_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_feature(user, "auto_rule_suggest")
    api = db.query(ParsedApi).filter(ParsedApi.id == api_id, ParsedApi.user_id == user.id).first()
    if not api:
        raise HTTPException(status_code=404, detail="API not found")
    return {"code": 0, "data": suggest_rule_from_api(api)}


@router.post("/sample-fields-from-response")
def sample_fields_from_response(payload: ResponseFieldsIn, user: User = Depends(get_current_user)):
    require_feature(user, "auto_field_detect")
    parsed, _ = parse_json_or_text(payload.response)
    if parsed is None:
        raise HTTPException(status_code=400, detail="Response 不是有效 JSON/JSONP，支持 {...}、[...]、callback({...})")
    candidates = sorted(find_arrays(parsed), key=lambda x: x.get('score', 0), reverse=True)
    selected_path = payload.response_list_path
    if not selected_path and candidates:
        selected_path = candidates[0].get('path') or ''
    item, root_count = find_sample_item(parsed, selected_path)
    if not item and not selected_path:
        item, root_count = find_sample_item(parsed, None)
    fields = flatten_fields(item) if item else []
    priority = {"nick": 1, "shopInfo.title": 2, "item_id": 3, "SkuId": 3, "wareId": 3, "realSales": 4, "price": 5, "priceShow.price": 6, "title": 7, "wareName": 7, "auctionURL": 8, "pic_path": 9}
    fields.sort(key=lambda f: (priority.get(f["path"], 999), f["path"]))
    return {"code": 0, "data": {"sampleApiId": None, "sampleUrl": "粘贴 Response", "rootCount": root_count, "responseListPath": selected_path, "listCandidates": [{"path": x.get('path'), "count": x.get('count'), "score": x.get('score')} for x in candidates[:8]], "fields": fields[:200]}}


@router.get("/sample-fields")
def sample_fields(
    urlPattern: str = Query('', description="接口 URL 匹配片段"),
    responseListPath: str | None = Query(None),
    method: str | None = Query(None),
    apiId: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_feature(user, "auto_field_detect")
    q = db.query(ParsedApi).filter(ParsedApi.user_id == user.id, ParsedApi.response_body.isnot(None))
    if apiId:
        q = q.filter(ParsedApi.id == apiId)
    else:
        if method:
            q = q.filter(ParsedApi.method == method.upper())
        if urlPattern:
            # sample 只做宽松 contains，regex/equals 在真正规则匹配时处理。
            q = q.filter(ParsedApi.url.ilike(f"%{urlPattern.strip()}%"))
    candidates = q.order_by(ParsedApi.created_at.desc(), ParsedApi.id.desc()).limit(30).all()
    for api in candidates:
        if urlPattern and not apiId and urlPattern not in api.url:
            # ilike 可能大小写命中；这里再兜底，不挡真正可用样本。
            pass
        item, root_count = find_sample_item(api.response_body, responseListPath)
        if not item:
            continue
        fields = flatten_fields(item)
        # 常用字段靠前，用户少滚点。
        priority = {"nick": 1, "shopInfo.title": 2, "item_id": 3, "realSales": 4, "price": 5, "priceShow.price": 6, "title": 7, "auctionURL": 8, "pic_path": 9}
        fields.sort(key=lambda f: (priority.get(f["path"], 999), f["path"]))
        return {"code": 0, "data": {"sampleApiId": api.id, "sampleUrl": api.url, "rootCount": root_count, "fields": fields[:200]}}
    return {"code": 0, "data": {"sampleApiId": None, "sampleUrl": None, "rootCount": 0, "fields": []}}


@router.get("/{rule_id}/test")
def test_rule(rule_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_feature(user, "rule_test")
    rule = db.query(CaptureRule).filter(CaptureRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    q = db.query(ParsedApi).filter(ParsedApi.user_id == user.id, ParsedApi.response_body.isnot(None))
    if rule.method:
        q = q.filter(ParsedApi.method == rule.method.upper())
    # 先用 contains 宽松缩小候选，再用真实 match_url 判断。
    if rule.url_pattern and rule.url_match_type == 'contains':
        q = q.filter(ParsedApi.url.ilike(f"%{rule.url_pattern.strip()}%"))
    candidates = q.order_by(ParsedApi.created_at.desc(), ParsedApi.id.desc()).limit(80).all()
    checked = 0
    diagnostics = []
    summary = {"urlFailed": 0, "methodFailed": 0, "paramsFailed": 0}
    for api in candidates:
        checked += 1
        url_ok = match_url(api.url or '', rule.url_pattern, rule.url_match_type)
        method_ok = (not rule.method) or rule.method.upper() == api.method
        params_ok = params_match(api.request_params, rule.params_filter)
        if not url_ok:
            summary["urlFailed"] += 1
        if not method_ok:
            summary["methodFailed"] += 1
        if not params_ok:
            summary["paramsFailed"] += 1
        if not (url_ok and method_ok and params_ok):
            if len(diagnostics) < 8:
                diagnostics.append({"apiId": api.id, "url": api.url, "method": api.method, "urlOk": url_ok, "methodOk": method_ok, "paramsOk": params_ok})
            continue
        root = get_path(api.response_body, rule.response_list_path)
        root_count = len(root) if isinstance(root, list) else (1 if isinstance(root, dict) else 0)
        parsed = parse_dynamic_rows_by_rule(api.response_body, rule, api.search_keyword)
        preview = [x['row_data'] for x in parsed[:20]]
        columns = []
        seen = set()
        for row in preview:
            for k in row.keys():
                if k not in seen:
                    seen.add(k); columns.append(k)
        mapping_checks = []
        sample_item = None
        if isinstance(root, list):
            sample_item = next((x for x in root if isinstance(x, dict)), None)
        elif isinstance(root, dict):
            sample_item = root
        mapping = rule.field_mapping or {}
        if isinstance(mapping, dict) and sample_item:
            for display_field, source_path, transform in normalize_field_specs([sample_item], mapping):
                raw_v = get_path(sample_item, str(source_path))
                mapping_checks.append({"left": display_field, "right": source_path, "leftHit": bool(display_field), "rightHit": raw_v is not None, "sample": preview_value(apply_value_transform(raw_v, transform)), "transform": transform})
        return {"code": 0, "data": {"matched": True, "apiId": api.id, "apiUrl": api.url, "checked": checked, "urlOk": url_ok, "methodOk": method_ok, "paramsOk": params_ok, "listPath": rule.response_list_path, "rootCount": root_count, "parsedCount": len(parsed), "columns": columns, "preview": preview, "mappingChecks": mapping_checks}}
    return {"code": 0, "data": {"matched": False, "checked": checked, "summary": summary, "diagnostics": diagnostics, "message": "没有找到最近可测试的命中接口；请检查 URL 匹配、请求方法或 Params 过滤。"}}

@router.post("")
def create_rule(payload: RuleIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    require_capacity(db, user, "rule", 1)
    if payload.url_match_type not in {"contains", "regex", "equals"}:
        raise HTTPException(status_code=400, detail="url_match_type must be contains/regex/equals")
    data = normalize_rule_payload(payload.model_dump())
    if data.get("label_id"):
        label = db.query(DataLabel).filter(DataLabel.id == data.get("label_id")).first()
        if not label:
            raise HTTPException(status_code=404, detail="Label not found")
        data["label_name"] = label.name
    rule = CaptureRule(user_id=user.id, creator_phone=user.phone, **data)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    # 创建者默认勾选自己新建的规则，其他用户可在 WebPC 手动勾选。
    db.add(UserRuleSelection(user_id=user.id, rule_id=rule.id))
    db.commit()
    return {"code": 0, "data": out_for_user(rule, user)}

@router.post("/{rule_id}/select")
def select_rule(rule_id: int, selected: bool = True, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rule = db.query(CaptureRule).filter(CaptureRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    row = db.query(UserRuleSelection).filter(UserRuleSelection.user_id == user.id, UserRuleSelection.rule_id == rule_id).first()
    if selected and not row:
        db.add(UserRuleSelection(user_id=user.id, rule_id=rule_id))
    if not selected and row:
        db.delete(row)
    db.commit()
    return {"code": 0, "ruleId": rule_id, "selected": selected}

@router.put("/{rule_id}")
def update_rule(rule_id: int, payload: RuleIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rule = db.query(CaptureRule).filter(CaptureRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    if rule.user_id != user.id:
        raise HTTPException(status_code=403, detail="Only creator can edit this rule")
    data = normalize_rule_payload(payload.model_dump())
    data["label_name"] = None
    if data.get("label_id"):
        label = db.query(DataLabel).filter(DataLabel.id == data.get("label_id")).first()
        if not label:
            raise HTTPException(status_code=404, detail="Label not found")
        data["label_name"] = label.name
    for k, v in data.items():
        setattr(rule, k, v)
    db.commit()
    db.refresh(rule)
    return {"code": 0, "data": out_for_user(rule, user)}

@router.delete("/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rule = db.query(CaptureRule).filter(CaptureRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    if rule.user_id != user.id:
        raise HTTPException(status_code=403, detail="Only creator can delete this rule")
    db.delete(rule)
    db.commit()
    return {"code": 0, "message": "删除成功"}
