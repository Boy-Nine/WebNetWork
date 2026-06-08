from __future__ import annotations
import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import and_
from ..database import get_db
from ..models import DataLabel, User
from ..utils.security import get_current_user, mask_phone

router = APIRouter(prefix="/api/labels", tags=["data labels"])

class LabelIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    table_name: str | None = None
    remark: str | None = None

def slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]+", "_", name.strip()).strip("_").lower()
    return f"label_{s or 'data'}"

def out(label: DataLabel, user: User):
    return {"id": label.id, "name": label.name, "table_name": label.table_name, "remark": label.remark, "creator_user_id": label.user_id, "creator_phone": mask_phone(label.creator_phone), "can_edit": label.user_id == user.id, "created_at": label.created_at}

@router.get("/list")
def list_labels(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(DataLabel).order_by(DataLabel.created_at.desc(), DataLabel.id.desc()).all()
    return {"code": 0, "data": [out(r, user) for r in rows]}

@router.post("")
def create_label(payload: LabelIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    table_name = payload.table_name or slugify(payload.name)
    label = DataLabel(user_id=user.id, creator_phone=user.phone, name=payload.name, table_name=table_name, remark=payload.remark)
    db.add(label)
    db.commit()
    db.refresh(label)
    return {"code": 0, "data": out(label, user)}

@router.delete("/{label_id}")
def delete_label(label_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    label = db.query(DataLabel).filter(DataLabel.id == label_id).first()
    if not label:
        raise HTTPException(status_code=404, detail="Label not found")
    if label.user_id != user.id:
        raise HTTPException(status_code=403, detail="Only creator can delete this label")
    db.delete(label)
    db.commit()
    return {"code": 0, "message": "删除成功"}
