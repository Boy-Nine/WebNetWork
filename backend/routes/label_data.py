from __future__ import annotations
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import Text
from ..database import get_db
from ..models import LabelDataRecord, DataLabel, User
from ..utils.security import get_current_user

router = APIRouter(prefix="/api/label-data", tags=["label data"])

def row_to_dict(r: LabelDataRecord, detail: bool = False):
    data = {
        "id": r.id,
        "label_id": r.label_id,
        "label_name": r.label_name,
        "rule_id": r.rule_id,
        "rule_name": r.rule_name,
        "row_data": r.row_data or {},
        "created_at": r.created_at,
    }
    if detail:
        data.update({"session_id": r.session_id, "api_id": r.api_id, "raw_item": r.raw_item})
    return data


def normalize_dt(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

def apply_label_filters(base, keyword: str | None, fieldFilters: str | None, startTime: datetime | None = None, endTime: datetime | None = None):
    if startTime:
        base = base.filter(LabelDataRecord.created_at >= normalize_dt(startTime))
    if endTime:
        base = base.filter(LabelDataRecord.created_at <= normalize_dt(endTime))
    if keyword:
        base = base.filter(LabelDataRecord.row_data.cast(Text).ilike(f"%{keyword.strip()}%"))
    if fieldFilters:
        try:
            filters = json.loads(fieldFilters)
        except Exception:
            raise HTTPException(status_code=400, detail="fieldFilters must be JSON object")
        if isinstance(filters, dict):
            for key, value in filters.items():
                if value not in (None, ''):
                    base = base.filter(LabelDataRecord.row_data[str(key)].astext.ilike(f"%{str(value).strip()}%"))
    return base

def collect_label_columns(db: Session, user_id: int, label_id: int) -> list[str]:
    # 列定义按整个标签表最近数据收集，避免分页/筛选导致列忽隐忽现。
    rows = db.query(LabelDataRecord.row_data).filter(LabelDataRecord.user_id == user_id, LabelDataRecord.label_id == label_id).order_by(LabelDataRecord.created_at.desc(), LabelDataRecord.id.desc()).limit(1000).all()
    seen, columns = set(), []
    preferred = ["搜索词", "店铺名称", "商品id", "skuId", "销量", "价格", "商品标题", "商品链接"]
    keys = []
    for (row_data,) in rows:
        keys.extend((row_data or {}).keys())
    for key in preferred + keys:
        if key in keys and key not in seen:
            seen.add(key); columns.append(key)
    return columns

@router.get("/list")
def list_label_data(
    labelId: int = Query(...),
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    keyword: str | None = None,
    fieldFilters: str | None = None,
    startTime: datetime | None = None,
    endTime: datetime | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    base = db.query(LabelDataRecord).filter(LabelDataRecord.user_id == user.id, LabelDataRecord.label_id == labelId)
    base = apply_label_filters(base, keyword, fieldFilters, startTime, endTime)
    total = base.count()
    rows = base.order_by(LabelDataRecord.created_at.desc(), LabelDataRecord.id.desc()).offset((page - 1) * pageSize).limit(pageSize).all()
    records = [row_to_dict(r) for r in rows]
    columns = collect_label_columns(db, user.id, labelId)
    return {"code": 0, "data": {"total": total, "columns": columns, "list": records}}

@router.get("/export")
def export_label_data(labelId: int, keyword: str | None = None, fieldFilters: str | None = None, startTime: datetime | None = None, endTime: datetime | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    base = db.query(LabelDataRecord).filter(LabelDataRecord.user_id == user.id, LabelDataRecord.label_id == labelId)
    base = apply_label_filters(base, keyword, fieldFilters, startTime, endTime)
    rows = base.order_by(LabelDataRecord.created_at.desc(), LabelDataRecord.id.desc()).limit(20000).all()
    records = [row_to_dict(r, detail=True) for r in rows]
    columns = collect_label_columns(db, user.id, labelId)
    return {"code": 0, "data": {"columns": columns, "list": records}}


@router.get("/{record_id}")
def detail_label_data(record_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.query(LabelDataRecord).filter(LabelDataRecord.id == record_id, LabelDataRecord.user_id == user.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Label data record not found")
    return {"code": 0, "data": row_to_dict(row, detail=True)}
