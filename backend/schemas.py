from __future__ import annotations
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field, field_validator
import re

PHONE_RE = re.compile(r"^\+?\d{5,20}$")

class UserCreate(BaseModel):
    phone: str = Field(min_length=5, max_length=20)
    password: str = Field(min_length=6, max_length=128)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not PHONE_RE.match(v):
            raise ValueError("手机号格式不正确")
        return v

class UserLogin(UserCreate):
    pass

class UserOut(BaseModel):
    id: int
    phone: str
    nickname: str | None = None
    class Config:
        from_attributes = True

class TokenOut(BaseModel):
    code: int = 0
    message: str = "success"
    token: str
    userId: int
    phone: str
    user: UserOut

class RegisterOut(BaseModel):
    code: int = 0
    message: str = "注册成功"
    userId: int

class CaptureUpload(BaseModel):
    url: str | None = None
    pageUrl: str | None = None
    title: str | None = None
    pageTitle: str | None = None
    htmlContent: str | None = None
    xhrList: list[dict[str, Any]] = Field(default_factory=list)
    captureTime: datetime | None = None
    startedAt: datetime | None = None
    endedAt: datetime | None = None

class CaptureListItem(BaseModel):
    id: int
    url: str
    page_title: str | None
    capture_time: datetime | None
    xhr_count: int
    created_at: datetime

class CaptureDetail(CaptureListItem):
    html_content: str | None
    xhr_data: list[dict[str, Any]]
    parsed_summary: dict[str, Any]

class ParsedApiListItem(BaseModel):
    id: int
    method: str
    url: str
    request_params: Any | None = None
    request_body_raw: str | None = None
    response_status: int | None = None
    response_body: Any | None = None
    response_body_text: str | None = None
    response_body_raw: str | None = None
    duration_ms: int | None = None
    host: str | None = None
    path: str | None = None
    query_params: Any | None = None
    content_type: str | None = None
    is_json: int | None = None
    response_size: int | None = None
    page_url: str | None = None
    page_title: str | None = None
    captured_at: datetime | None = None
    created_at: datetime

class ParsedApiDetail(ParsedApiListItem):
    session_id: int | None = None
    request_headers: dict[str, Any] | None = None
    response_headers: dict[str, Any] | None = None
