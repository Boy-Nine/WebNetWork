from __future__ import annotations
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import CaptureRule, DataLabel, User, UserRuleSelection, ParsedApi
from ..utils.security import get_current_user, mask_phone
from ..utils.rule_engine import get_path, match_url, params_match, parse_dynamic_rows_by_rule, normalize_field_specs, apply_value_transform

router = APIRouter(prefix="/api/rules", tags=["capture rules"])


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
    if normalize_key(p) in FIELD_LABEL_HINTS:
        return FIELD_LABEL_HINTS[normalize_key(p)]
    tail = p.split('.')[-1]
    if normalize_key(tail) in FIELD_LABEL_HINTS:
        return FIELD_LABEL_HINTS[normalize_key(tail)]
    return tail

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
                # 对对象本身不作为字段，只展开子字段。
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


@router.get("/sample-fields")
def sample_fields(
    urlPattern: str = Query('', description="接口 URL 匹配片段"),
    responseListPath: str | None = Query(None),
    method: str | None = Query(None),
    apiId: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
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
    for api in candidates:
        checked += 1
        url_ok = match_url(api.url or '', rule.url_pattern, rule.url_match_type)
        method_ok = (not rule.method) or rule.method.upper() == api.method
        params_ok = params_match(api.request_params, rule.params_filter)
        if not (url_ok and method_ok and params_ok):
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
    return {"code": 0, "data": {"matched": False, "checked": checked, "message": "没有找到最近可测试的命中接口；请先用插件捕获并上报一次。"}}

@router.post("")
def create_rule(payload: RuleIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
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
