from __future__ import annotations
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from ..config import settings
from ..database import get_db
from ..models import CaptureRecord, CaptureSession, ParsedApi, ChannelProductRecord, LabelDataRecord, CaptureRule, UserRuleSelection, User
from ..schemas import CaptureDetail, CaptureUpload
from ..utils.security import get_current_user
from ..utils.parser import parse_capture
from ..utils.api_parser import build_parsed_api
from ..utils.channel_parser import parse_channel_records
from ..utils.rule_engine import find_matching_rule, parse_by_rule, parse_dynamic_rows_by_rule
from ..utils.membership import require_capacity, export_limit, membership_payload

router = APIRouter(tags=["capture"])

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def byte_len(s: str | None) -> int:
    return len((s or "").encode("utf-8"))

def truncate_text(value, max_bytes: int) -> str | None:
    if value is None:
        return None
    text = value if isinstance(value, str) else str(value)
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return text
    return raw[:max_bytes].decode("utf-8", errors="ignore") + "\n...[truncated]"

def normalize_dt(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value

def effective_capture_time(r: CaptureRecord):
    return r.capture_time or r.created_at

def validate_and_normalize(payload: CaptureUpload) -> list[dict]:
    if payload.htmlContent and byte_len(payload.htmlContent) > settings.max_html_bytes:
        raise HTTPException(status_code=413, detail=f"htmlContent exceeds {settings.max_html_size_mb}MB")
    if len(payload.xhrList or []) > settings.max_xhr_items:
        raise HTTPException(status_code=413, detail=f"xhrList exceeds {settings.max_xhr_items} items")
    normalized = []
    for item in payload.xhrList or []:
        copied = dict(item)
        for key in ("responseBody", "requestBody"):
            if copied.get(key) is not None:
                copied[key] = truncate_text(copied.get(key), settings.max_response_body_bytes)
        normalized.append(copied)
    return normalized

def record_to_out(r: CaptureRecord):
    return {
        "id": r.id,
        "url": r.url,
        "page_title": r.page_title,
        "capture_time": effective_capture_time(r),
        "xhr_count": len(r.xhr_data or []),
        "created_at": r.created_at,
    }

def resolve_time_params(start_time, end_time, start_alias, end_alias):
    return normalize_dt(start_time or start_alias), normalize_dt(end_time or end_alias)

def apply_filters(q, current_user: User, start_time: datetime | None, end_time: datetime | None, url_keyword: str | None):
    q = q.filter(CaptureRecord.user_id == current_user.id)
    # capture_time 正常都会写入；兼容旧/异常数据，capture_time 为空时按 created_at 查。
    if start_time:
        q = q.filter(or_(CaptureRecord.capture_time >= start_time, and_(CaptureRecord.capture_time.is_(None), CaptureRecord.created_at >= start_time)))
    if end_time:
        q = q.filter(or_(CaptureRecord.capture_time <= end_time, and_(CaptureRecord.capture_time.is_(None), CaptureRecord.created_at <= end_time)))
    if url_keyword:
        q = q.filter(CaptureRecord.url.ilike(f"%{url_keyword.strip()}%"))
    return q

@router.post("/api/capture/upload")
def upload_capture(payload: CaptureUpload, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    xhr_list = validate_and_normalize(payload)
    require_capacity(db, user, "upload", len(xhr_list))
    summary = parse_capture(xhr_list)
    record = CaptureRecord(
        user_id=user.id,
        url=payload.url or payload.pageUrl or "",
        page_title=payload.title or payload.pageTitle,
        html_content=payload.htmlContent,
        xhr_data=xhr_list,
        parsed_summary=summary,
        capture_time=normalize_dt(payload.captureTime) or utc_now(),
    )
    page_url = payload.url or payload.pageUrl or ""
    page_title = payload.title or payload.pageTitle
    started_at = normalize_dt(payload.startedAt)
    ended_at = normalize_dt(payload.endedAt) or utc_now()
    captured_at = started_at or normalize_dt(payload.captureTime) or ended_at
    session = CaptureSession(
        user_id=user.id,
        page_url=page_url,
        page_title=page_title,
        html_snapshot=payload.htmlContent,
        started_at=started_at,
        ended_at=ended_at,
        captured_at=captured_at,
    )
    db.add(record)
    db.add(session)
    db.flush()
    # 规则公共可见，但只对当前用户已勾选的启用规则生效。
    selected_rule_ids = [x.rule_id for x in db.query(UserRuleSelection).filter(UserRuleSelection.user_id == user.id).all()]
    rules = db.query(CaptureRule).filter(CaptureRule.enabled == 1, CaptureRule.id.in_(selected_rule_ids)).order_by(CaptureRule.id.desc()).all() if selected_rule_ids else []
    parsed_rows = []
    channel_rows = []
    label_rows = []
    skipped_rows = []
    for idx, item in enumerate(xhr_list):
        try:
            api_data = build_parsed_api(
                item,
                user_id=user.id,
                session_id=session.id,
                page_url=page_url,
                page_title=page_title,
                fallback_time=captured_at,
                max_body_bytes=settings.max_response_body_bytes,
            )
            rule = find_matching_rule(api_data, rules)
            # 只要当前用户启用了插件规则，就只允许命中规则的接口入库。
            # 插件侧也会过滤，但后端必须兜底，避免上报包混入无关接口后污染 WebPC。
            if rules and not rule:
                skipped_rows.append({
                    "index": idx,
                    "url": api_data.get("url"),
                    "method": api_data.get("method"),
                    "reason": "not_matched_rule",
                })
                continue
            if rule:
                api_data["matched_rule_id"] = rule.id
                api_data["matched_rule_name"] = rule.name
                api_data["label_id"] = rule.label_id
                api_data["label_name"] = rule.label_name
            api_row = ParsedApi(**api_data)
            db.add(api_row)
            db.flush()
            parsed_rows.append(api_row)
            # 优先按用户在 WebPC 配置的规则解析；未配置/未命中时走通用自动解析。
            mapped_items = parse_by_rule(api_data.get("response_body"), rule, fallback_search_keyword=api_data.get("search_keyword")) if rule else []
            if not mapped_items:
                mapped_items = parse_channel_records(api_data.get("response_body"), fallback_search_keyword=api_data.get("search_keyword"))
            for mapped in mapped_items:
                channel_rows.append(ChannelProductRecord(user_id=user.id, session_id=session.id, api_id=api_row.id, label_id=api_data.get("label_id"), label_name=api_data.get("label_name"), **mapped))
            if rule and rule.label_id:
                for dynamic in parse_dynamic_rows_by_rule(api_data.get("response_body"), rule, fallback_search_keyword=api_data.get("search_keyword")):
                    label_rows.append(LabelDataRecord(
                        user_id=user.id,
                        session_id=session.id,
                        api_id=api_row.id,
                        label_id=rule.label_id,
                        label_name=rule.label_name,
                        rule_id=rule.id,
                        rule_name=rule.name,
                        row_data=dynamic["row_data"],
                        raw_item=dynamic["raw_item"],
                    ))
        except Exception as exc:
            skipped_rows.append({"index": idx, "url": item.get("url") if isinstance(item, dict) else None, "error": str(exc)[:300]})
            continue
    db.add_all(channel_rows)
    db.add_all(label_rows)
    db.commit()
    db.refresh(record)
    return {"code": 0, "message": "上传成功", "recordId": record.id, "sessionId": session.id, "insertedCount": len(parsed_rows), "apiCount": len(parsed_rows), "channelRecordCount": len(channel_rows), "labelRecordCount": len(label_rows), "skippedCount": len(skipped_rows), "skipped": skipped_rows[:20], "summary": summary, "membership": membership_payload(db, user)}

@router.get("/api/data/list")
def list_data(
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    startTime: datetime | None = None,
    endTime: datetime | None = None,
    urlKeyword: str | None = None,
    # 兼容常见命名，方便插件/脚本调用。
    start: datetime | None = None,
    end: datetime | None = None,
    keyword: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    start_time, end_time = resolve_time_params(startTime, endTime, start, end)
    base = apply_filters(db.query(CaptureRecord), user, start_time, end_time, urlKeyword or keyword)
    total = base.count()
    rows = base.order_by(CaptureRecord.capture_time.desc().nullslast(), CaptureRecord.created_at.desc(), CaptureRecord.id.desc()).offset((page - 1) * pageSize).limit(pageSize).all()
    return {"code": 0, "data": {"total": total, "list": [record_to_out(r) for r in rows]}}

@router.get("/api/data/export")
def export_data(
    startTime: datetime | None = None,
    endTime: datetime | None = None,
    urlKeyword: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    keyword: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    start_time, end_time = resolve_time_params(startTime, endTime, start, end)
    rows = apply_filters(db.query(CaptureRecord), user, start_time, end_time, urlKeyword or keyword).order_by(CaptureRecord.capture_time.desc().nullslast(), CaptureRecord.created_at.desc(), CaptureRecord.id.desc()).limit(export_limit(user)).all()
    return {"code": 0, "data": [
        {**record_to_out(r), "xhr_summary": [
            {"method": x.get("method"), "url": x.get("url"), "status": x.get("responseStatus", x.get("status")), "responseBody": truncate_text(x.get("responseBody"), 500)}
            for x in (r.xhr_data or [])[:100]
        ]}
        for r in rows
    ]}

@router.get("/api/data/{record_id}", response_model=CaptureDetail)
def data_detail(record_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    r = db.query(CaptureRecord).filter(and_(CaptureRecord.id == record_id, CaptureRecord.user_id == user.id)).first()
    if not r:
        raise HTTPException(status_code=404, detail="Record not found")
    return {**record_to_out(r), "html_content": r.html_content, "xhr_data": r.xhr_data or [], "parsed_summary": r.parsed_summary or {}}


@router.delete("/api/data/{record_id}")
def delete_record(record_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    r = db.query(CaptureRecord).filter(and_(CaptureRecord.id == record_id, CaptureRecord.user_id == user.id)).first()
    if not r:
        raise HTTPException(status_code=404, detail="Record not found")
    db.delete(r)
    db.commit()
    return {"code": 0, "message": "删除成功", "recordId": record_id}
