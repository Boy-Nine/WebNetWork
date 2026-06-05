from __future__ import annotations
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from ..database import get_db
from ..models import ParsedApi, User, CaptureRule
from ..utils.security import get_current_user
from ..utils.api_parser import truncate_text
from ..utils.rule_engine import parse_dynamic_rows_by_rule

router = APIRouter(prefix="/api/apis", tags=["parsed apis"])

def normalize_dt(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

def api_to_out(row: ParsedApi, detail: bool = False):
    data = {
        "id": row.id,
        "method": row.method,
        "url": row.url,
        "request_params": row.request_params,
        "search_keyword": row.search_keyword,
        "matched_rule_id": row.matched_rule_id,
        "matched_rule_name": row.matched_rule_name,
        "label_id": row.label_id,
        "label_name": row.label_name,
        "request_body_raw": truncate_text(row.request_body_raw, 1000) if not detail else row.request_body_raw,
        "response_status": row.response_status,
        "response_body": row.response_body,
        "response_body_text": truncate_text(row.response_body_text, 1000) if not detail else row.response_body_text,
        "response_body_raw": truncate_text(row.response_body_raw, 1000) if not detail else row.response_body_raw,
        "duration_ms": row.duration_ms,
        "host": row.host,
        "path": row.path,
        "query_params": row.query_params,
        "content_type": row.content_type,
        "is_json": row.is_json,
        "response_size": row.response_size,
        "page_url": row.page_url,
        "page_title": row.page_title,
        "captured_at": row.captured_at,
        "created_at": row.created_at,
    }
    if detail:
        data.update({
            "session_id": row.session_id,
            "request_headers": row.request_headers,
            "response_headers": row.response_headers,
        })
    return data

def apply_api_filters(q, user: User, start_time, end_time, api_url_keyword, page_url_keyword, method, status_code, failed_only=False, min_duration_ms=None, search_keyword=None, label_id=None, label_name=None):
    q = q.filter(ParsedApi.user_id == user.id)
    if start_time:
        q = q.filter(ParsedApi.captured_at >= start_time)
    if end_time:
        q = q.filter(ParsedApi.captured_at <= end_time)
    if api_url_keyword:
        q = q.filter(ParsedApi.url.ilike(f"%{api_url_keyword.strip()}%"))
    if page_url_keyword:
        q = q.filter(ParsedApi.page_url.ilike(f"%{page_url_keyword.strip()}%"))
    if search_keyword:
        q = q.filter(ParsedApi.search_keyword.ilike(f"%{search_keyword.strip()}%"))
    if label_id is not None:
        q = q.filter(ParsedApi.label_id == label_id)
    if label_name:
        q = q.filter(ParsedApi.label_name.ilike(f"%{label_name.strip()}%"))
    if method:
        q = q.filter(ParsedApi.method == method.upper())
    if status_code is not None:
        q = q.filter(ParsedApi.response_status == status_code)
    if failed_only:
        q = q.filter(ParsedApi.response_status >= 400)
    if min_duration_ms is not None:
        q = q.filter(ParsedApi.duration_ms >= min_duration_ms)
    return q


@router.get("/stats")
def api_stats(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    base = db.query(ParsedApi).filter(ParsedApi.user_id == user.id)
    total = base.count()
    ok2xx = base.filter(ParsedApi.response_status >= 200, ParsedApi.response_status < 300).count()
    failed = base.filter(ParsedApi.response_status >= 400).count()
    slow = base.filter(ParsedApi.duration_ms >= 1000).count()
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today = base.filter(ParsedApi.captured_at >= today_start).count()
    method_rows = db.query(ParsedApi.method, func.count(ParsedApi.id)).filter(ParsedApi.user_id == user.id).group_by(ParsedApi.method).all()
    top_hosts = db.query(ParsedApi.host, func.count(ParsedApi.id).label("count")).filter(ParsedApi.user_id == user.id, ParsedApi.host.isnot(None)).group_by(ParsedApi.host).order_by(func.count(ParsedApi.id).desc()).limit(8).all()
    latest = base.order_by(ParsedApi.captured_at.desc().nullslast(), ParsedApi.created_at.desc(), ParsedApi.id.desc()).first()
    return {"code": 0, "data": {
        "total": total,
        "ok2xx": ok2xx,
        "failed": failed,
        "slow": slow,
        "today": today,
        "methods": {m or "UNKNOWN": c for m, c in method_rows},
        "topHosts": [{"host": h or "-", "count": c} for h, c in top_hosts],
        "latest": api_to_out(latest) if latest else None,
    }}

@router.get("/list")
def list_apis(
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    startTime: datetime | None = None,
    endTime: datetime | None = None,
    urlKeyword: str | None = None,
    apiUrlKeyword: str | None = None,
    pageUrlKeyword: str | None = None,
    searchKeyword: str | None = None,
    labelId: int | None = None,
    labelName: str | None = None,
    method: str | None = None,
    statusCode: int | None = None,
    failedOnly: bool = False,
    minDurationMs: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    base = apply_api_filters(db.query(ParsedApi), user, normalize_dt(startTime), normalize_dt(endTime), apiUrlKeyword or urlKeyword, pageUrlKeyword, method, statusCode, failedOnly, minDurationMs, searchKeyword, labelId, labelName)
    total = base.count()
    rows = base.order_by(ParsedApi.captured_at.desc().nullslast(), ParsedApi.created_at.desc(), ParsedApi.id.desc()).offset((page - 1) * pageSize).limit(pageSize).all()
    return {"code": 0, "data": {"total": total, "list": [api_to_out(r) for r in rows]}}

@router.get("/export")
def export_apis(
    startTime: datetime | None = None,
    endTime: datetime | None = None,
    urlKeyword: str | None = None,
    apiUrlKeyword: str | None = None,
    pageUrlKeyword: str | None = None,
    searchKeyword: str | None = None,
    labelId: int | None = None,
    labelName: str | None = None,
    method: str | None = None,
    statusCode: int | None = None,
    failedOnly: bool = False,
    minDurationMs: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = apply_api_filters(db.query(ParsedApi), user, normalize_dt(startTime), normalize_dt(endTime), apiUrlKeyword or urlKeyword, pageUrlKeyword, method, statusCode, failedOnly, minDurationMs, searchKeyword, labelId, labelName).order_by(ParsedApi.captured_at.desc().nullslast(), ParsedApi.created_at.desc(), ParsedApi.id.desc()).limit(20000).all()
    return {"code": 0, "data": [api_to_out(r, detail=True) for r in rows]}

@router.get("/{api_id}")
def api_detail(api_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.query(ParsedApi).filter(and_(ParsedApi.id == api_id, ParsedApi.user_id == user.id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="API record not found")
    data = api_to_out(row, detail=True)
    data["parsed_preview"] = []
    data["parsed_preview_columns"] = []
    data["parsed_rule"] = None
    if row.matched_rule_id:
        rule = db.query(CaptureRule).filter(CaptureRule.id == row.matched_rule_id).first()
        if rule:
            parsed = parse_dynamic_rows_by_rule(row.response_body, rule, fallback_search_keyword=row.search_keyword)
            preview = [x["row_data"] for x in parsed[:50]]
            cols = []
            seen = set()
            for item in preview:
                for k in (item or {}).keys():
                    if k not in seen:
                        seen.add(k); cols.append(k)
            data["parsed_preview"] = preview
            data["parsed_preview_columns"] = cols
            data["parsed_rule"] = {"id": rule.id, "name": rule.name, "label_id": rule.label_id, "label_name": rule.label_name}
    return data

@router.delete("/{api_id}")
def delete_api(api_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.query(ParsedApi).filter(and_(ParsedApi.id == api_id, ParsedApi.user_id == user.id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="API record not found")
    db.delete(row)
    db.commit()
    return {"code": 0, "message": "删除成功", "apiId": api_id}
