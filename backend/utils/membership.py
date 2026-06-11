from __future__ import annotations
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from ..models import User, ParsedApi, CaptureRule, DataLabel

FEATURE_LABELS = {
    "basic_capture": "基础捕获",
    "basic_query": "基础查询",
    "manual_rules": "手写规则",
    "basic_export": "基础导出",
    "auto_rule_suggest": "从接口生成规则",
    "auto_field_detect": "自动识别字段",
    "curl_import": "cURL 导入规则",
    "rule_test": "规则测试诊断",
    "advanced_label_filter": "高级字段筛选",
    "batch_delete": "批量删除",
    "team_quota": "团队级额度",
}

PLAN_LIMITS = {
    "free": {
        "name": "免费版",
        "price": 0,
        "monthly_api_limit": 1000,
        "per_upload_limit": 50,
        "rule_limit": 5,
        "label_limit": 3,
        "export_limit": 500,
        "enabled_features": ["basic_capture", "basic_query", "manual_rules", "basic_export"],
        "features": ["基础接口捕获", "基础查询筛选", "手写规则", "少量导出"],
    },
    "pro": {
        "name": "专业版",
        "price": 0.01,
        "monthly_api_limit": 30000,
        "per_upload_limit": 200,
        "rule_limit": 50,
        "label_limit": 30,
        "export_limit": 10000,
        "enabled_features": ["basic_capture", "basic_query", "manual_rules", "basic_export", "auto_rule_suggest", "auto_field_detect", "curl_import", "rule_test", "advanced_label_filter"],
        "features": ["自动生成规则", "自动识别字段", "导入 cURL", "规则测试诊断", "高级字段筛选", "大批量导出"],
    },
    "team": {
        "name": "团队版",
        "price": 0.02,
        "monthly_api_limit": 200000,
        "per_upload_limit": 500,
        "rule_limit": 300,
        "label_limit": 200,
        "export_limit": 50000,
        "enabled_features": ["basic_capture", "basic_query", "manual_rules", "basic_export", "auto_rule_suggest", "auto_field_detect", "curl_import", "rule_test", "advanced_label_filter", "batch_delete", "team_quota"],
        "features": ["团队级额度", "批量删除", "海量规则/标签", "超大导出", "可扩展支付/成员管理"],
    },
}


def current_plan(user: User) -> str:
    plan = getattr(user, "membership_plan", None) or "free"
    expires_at = getattr(user, "membership_expires_at", None)
    if plan != "free" and expires_at and expires_at < datetime.now(timezone.utc):
        return "free"
    return plan if plan in PLAN_LIMITS else "free"


def limits_for(user: User) -> dict:
    plan = current_plan(user)
    return {"plan": plan, **PLAN_LIMITS[plan]}


def feature_flags(user: User) -> dict[str, bool]:
    enabled = set(limits_for(user).get("enabled_features") or [])
    return {key: key in enabled for key in FEATURE_LABELS}


def has_feature(user: User, feature: str) -> bool:
    return feature_flags(user).get(feature, False)


def require_feature(user: User, feature: str) -> None:
    if not has_feature(user, feature):
        label = FEATURE_LABELS.get(feature, feature)
        raise HTTPException(status_code=402, detail=f"当前套餐不支持「{label}」，请升级会员")


def month_start() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def usage_for(db: Session, user: User) -> dict:
    start = month_start()
    return {
        "monthly_api_count": db.query(func.count(ParsedApi.id)).filter(ParsedApi.user_id == user.id, ParsedApi.created_at >= start).scalar() or 0,
        "rule_count": db.query(func.count(CaptureRule.id)).filter(CaptureRule.user_id == user.id).scalar() or 0,
        "label_count": db.query(func.count(DataLabel.id)).filter(DataLabel.user_id == user.id).scalar() or 0,
    }


def membership_payload(db: Session, user: User) -> dict:
    limits = limits_for(user)
    usage = usage_for(db, user)
    return {
        "plan": limits["plan"],
        "planName": limits["name"],
        "expiresAt": getattr(user, "membership_expires_at", None),
        "limits": {k: limits[k] for k in ("monthly_api_limit", "per_upload_limit", "rule_limit", "label_limit", "export_limit")},
        "usage": usage,
        "features": feature_flags(user),
        "featureLabels": FEATURE_LABELS,
    }


def require_capacity(db: Session, user: User, kind: str, adding: int = 1) -> None:
    limits = limits_for(user)
    usage = usage_for(db, user)
    if kind == "upload":
        if adding > limits["per_upload_limit"]:
            raise HTTPException(status_code=402, detail=f"当前套餐单次最多上报 {limits['per_upload_limit']} 个接口，请升级会员或减少本次上报数量")
        if usage["monthly_api_count"] + adding > limits["monthly_api_limit"]:
            raise HTTPException(status_code=402, detail=f"本月接口入库额度已不足：{usage['monthly_api_count']}/{limits['monthly_api_limit']}，请升级会员")
    elif kind == "rule":
        if usage["rule_count"] + adding > limits["rule_limit"]:
            raise HTTPException(status_code=402, detail=f"当前套餐最多创建 {limits['rule_limit']} 条规则，请升级会员")
    elif kind == "label":
        if usage["label_count"] + adding > limits["label_limit"]:
            raise HTTPException(status_code=402, detail=f"当前套餐最多创建 {limits['label_limit']} 个标签，请升级会员")


def export_limit(user: User) -> int:
    return int(limits_for(user)["export_limit"])


def activate_membership(user: User, plan: str, days: int = 31) -> None:
    if plan not in PLAN_LIMITS:
        raise HTTPException(status_code=400, detail="无效套餐")
    user.membership_plan = plan
    user.membership_expires_at = None if plan == "free" else datetime.now(timezone.utc) + timedelta(days=days)
