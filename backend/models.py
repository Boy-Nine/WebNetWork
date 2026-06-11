from __future__ import annotations
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    phone: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    nickname: Mapped[str | None] = mapped_column(String(64), nullable=True)
    membership_plan: Mapped[str] = mapped_column(String(32), nullable=False, default="free", server_default="free", index=True)
    membership_expires_at = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    records = relationship("CaptureRecord", back_populates="user")
    sessions = relationship("CaptureSession", back_populates="user")
    parsed_apis = relationship("ParsedApi", back_populates="user")

class CaptureRecord(Base):
    __tablename__ = "capture_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    page_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    html_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    xhr_data = mapped_column(JSONB, nullable=False, default=list)
    parsed_summary = mapped_column(JSONB, nullable=False, default=dict)
    capture_time = mapped_column(DateTime(timezone=True), nullable=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    user = relationship("User", back_populates="records")

class CaptureSession(Base):
    __tablename__ = "capture_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    page_url: Mapped[str] = mapped_column(Text, nullable=False)
    page_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    html_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    ended_at = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    captured_at = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    user = relationship("User", back_populates="sessions")
    parsed_apis = relationship("ParsedApi", back_populates="session", cascade="all, delete-orphan")

class ParsedApi(Base):
    __tablename__ = "captured_apis"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("capture_sessions.id", ondelete="CASCADE"), index=True, nullable=True)
    method: Mapped[str] = mapped_column(String(12), index=True, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    request_headers = mapped_column(JSONB, nullable=True)
    response_headers = mapped_column(JSONB, nullable=True)
    request_params = mapped_column(JSONB, nullable=True)
    query_params = mapped_column(JSONB, nullable=True)
    search_keyword: Mapped[str | None] = mapped_column(Text, nullable=True)
    matched_rule_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    matched_rule_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    label_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    label_name: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    host: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    path: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_json: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_body_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_status: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    response_body = mapped_column(JSONB, nullable=True)
    response_body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_body_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    captured_at = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    user = relationship("User", back_populates="parsed_apis")
    session = relationship("CaptureSession", back_populates="parsed_apis")


class ChannelProductRecord(Base):
    __tablename__ = "channel_product_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("capture_sessions.id", ondelete="CASCADE"), index=True, nullable=True)
    api_id: Mapped[int | None] = mapped_column(ForeignKey("captured_apis.id", ondelete="CASCADE"), index=True, nullable=True)
    label_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    label_name: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    platform_user: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_created_at: Mapped[str | None] = mapped_column(String(255), nullable=True)
    search_keyword: Mapped[str | None] = mapped_column(Text, nullable=True)
    channel_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    channel_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    sku_id: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    price: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sales: Mapped[str | None] = mapped_column(String(255), nullable=True)
    channel_image: Mapped[str | None] = mapped_column(Text, nullable=True)
    shop_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    shop_id: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    shop_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    ad_tag: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_activity: Mapped[str | None] = mapped_column(Text, nullable=True)
    discount_strength: Mapped[str | None] = mapped_column(Text, nullable=True)
    platform_category: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    ranking_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    ship_from: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_marketing: Mapped[str | None] = mapped_column(Text, nullable=True)
    shop_marketing: Mapped[str | None] = mapped_column(Text, nullable=True)
    article_number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    core_tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    activity_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    channel_page_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    shop_tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_item = mapped_column(JSONB, nullable=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class CaptureRule(Base):
    __tablename__ = "capture_rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    creator_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    label_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    label_name: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    method: Mapped[str | None] = mapped_column(String(12), nullable=True)
    url_pattern: Mapped[str] = mapped_column(Text, nullable=False)
    url_match_type: Mapped[str] = mapped_column(String(20), nullable=False, default="contains")
    params_filter = mapped_column(JSONB, nullable=True)
    response_list_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    field_mapping = mapped_column(JSONB, nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class UserRuleSelection(Base):
    __tablename__ = "user_rule_selections"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    rule_id: Mapped[int] = mapped_column(ForeignKey("capture_rules.id", ondelete="CASCADE"), index=True, nullable=False)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class DataLabel(Base):
    __tablename__ = "data_labels"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    creator_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    table_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class LabelDataRecord(Base):
    __tablename__ = "label_data_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("capture_sessions.id", ondelete="CASCADE"), index=True, nullable=True)
    api_id: Mapped[int | None] = mapped_column(ForeignKey("captured_apis.id", ondelete="CASCADE"), index=True, nullable=True)
    label_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    label_name: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    rule_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    rule_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    row_data = mapped_column(JSONB, nullable=False, default=dict)
    raw_item = mapped_column(JSONB, nullable=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class MembershipOrder(Base):
    __tablename__ = "membership_orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    order_no: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    plan: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    plan_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    days: Mapped[int] = mapped_column(Integer, nullable=False, default=31)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    pay_channel: Mapped[str | None] = mapped_column(String(32), nullable=True)
    code_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    transaction_id: Mapped[str | None] = mapped_column(String(96), nullable=True, index=True)
    paid_at = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), index=True)
