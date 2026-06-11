from __future__ import annotations
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from ..config import settings
from ..database import get_db
from ..models import User, MembershipOrder
from ..utils.security import get_current_user, mask_phone
from ..utils.membership import PLAN_LIMITS, membership_payload, activate_membership, usage_for
from ..utils.wechat_pay import WechatPayClient, WechatPayConfig

router = APIRouter(prefix="/api/membership", tags=["membership"])

ORDER_TTL_MINUTES = 10
PENDING_ORDER_TTL = timedelta(minutes=ORDER_TTL_MINUTES)

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def normalize_dt(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

def order_expires_at(order: MembershipOrder) -> datetime | None:
    created = normalize_dt(order.created_at)
    return created + PENDING_ORDER_TTL if created else None

def expire_pending_orders(db: Session, user_id: int | None = None) -> int:
    cutoff = now_utc() - PENDING_ORDER_TTL
    q = db.query(MembershipOrder).filter(MembershipOrder.status == "pending")
    if user_id is not None:
        q = q.filter(MembershipOrder.user_id == user_id)
    rows = q.filter(MembershipOrder.created_at <= cutoff).all()
    for row in rows:
        row.status = "canceled"
        row.pay_channel = row.pay_channel or "timeout"
    if rows:
        db.commit()
    return len(rows)

def active_pending_order(db: Session, user_id: int) -> MembershipOrder | None:
    expire_pending_orders(db, user_id)
    return (
        db.query(MembershipOrder)
        .filter(MembershipOrder.user_id == user_id, MembershipOrder.status == "pending")
        .order_by(MembershipOrder.created_at.desc(), MembershipOrder.id.desc())
        .first()
    )


class GrantMembershipIn(BaseModel):
    phone: str | None = None
    user_id: int | None = None
    plan: str = Field(pattern="^(free|pro|team)$")
    days: int = Field(default=31, ge=1, le=3660)

class ConfirmOrderIn(BaseModel):
    pay_channel: str | None = "manual"


def assert_admin_key(x_admin_key: str | None) -> None:
    if not x_admin_key or x_admin_key != settings.membership_admin_key:
        raise HTTPException(status_code=403, detail="Invalid membership admin key")


def order_out(order: MembershipOrder):
    expires_at = order_expires_at(order) if order.status == "pending" else None
    return {
        "id": order.id,
        "orderNo": order.order_no,
        "userId": order.user_id,
        "phone": mask_phone(order.phone),
        "plan": order.plan,
        "planName": order.plan_name,
        "amount": round((order.amount_cents or 0) / 100, 2),
        "amountCents": order.amount_cents,
        "days": order.days,
        "status": order.status,
        "payChannel": order.pay_channel,
        "codeUrl": order.code_url,
        "transactionId": order.transaction_id,
        "paidAt": order.paid_at,
        "createdAt": order.created_at,
        "updatedAt": order.updated_at,
        "expiresAt": expires_at,
        "ttlSeconds": max(0, int((expires_at - now_utc()).total_seconds())) if expires_at else 0,
    }


def mark_order_paid(db: Session, order: MembershipOrder, *, transaction_id: str | None = None, paid_at: datetime | None = None) -> MembershipOrder:
    user = db.get(User, order.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    order.status = "paid"
    order.pay_channel = "wechat_native"
    order.transaction_id = transaction_id or order.transaction_id
    order.paid_at = paid_at or now_utc()
    activate_membership(user, order.plan, order.days)
    db.commit()
    db.refresh(order)
    return order


def sync_wechat_order_status(db: Session, order: MembershipOrder) -> tuple[MembershipOrder, str]:
    if order.status != "pending" or order.pay_channel != "wechat_native":
        return order, order.status
    result = WechatPayClient(WechatPayConfig.from_settings(settings)).query_order(out_trade_no=order.order_no)
    trade_state = result.get("trade_state") or ""
    if trade_state == "SUCCESS":
        amount = result.get("amount") or {}
        payer_total = int(amount.get("payer_total") or amount.get("total") or 0)
        if payer_total != int(order.amount_cents):
            raise HTTPException(status_code=409, detail="微信支付金额与订单金额不一致，请联系管理员")
        order = mark_order_paid(db, order, transaction_id=result.get("transaction_id"))
    elif trade_state in {"CLOSED", "REVOKED", "PAYERROR"}:
        order.status = "canceled"
        order.pay_channel = f"wechat_{trade_state.lower()}"
        db.commit()
        db.refresh(order)
    return order, trade_state


@router.get("/plans")
def plans():
    return {"code": 0, "data": [{"key": key, **value} for key, value in PLAN_LIMITS.items()]}


@router.get("/me")
def my_membership(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return {"code": 0, "data": membership_payload(db, user)}


@router.post("/checkout")
def checkout(plan: str, days: int = Query(31, ge=1, le=3660), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if plan not in PLAN_LIMITS or plan == "free":
        raise HTTPException(status_code=400, detail="请选择有效的付费套餐")
    if not settings.wechat_pay_enabled:
        raise HTTPException(status_code=503, detail="微信支付未启用，请检查 WECHAT_PAY_ENABLED")
    pending = active_pending_order(db, user.id)
    if pending:
        if pending.code_url:
            return {"code": 0, "data": {**order_out(pending), "reused": True, "message": "你已有 10 分钟内有效的待支付订单，请继续扫码支付"}}
        order = pending
        reused = True
    else:
        plan_info = PLAN_LIMITS[plan]
        order = MembershipOrder(
            order_no=f"VIP{now_utc().strftime('%Y%m%d%H%M%S')}{uuid4().hex[:8].upper()}",
            user_id=user.id,
            phone=user.phone,
            plan=plan,
            plan_name=plan_info["name"],
            amount_cents=int(plan_info["price"] * 100),
            days=days,
            status="pending",
            pay_channel="wechat_native",
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        reused = False
    try:
        client = WechatPayClient(WechatPayConfig.from_settings(settings))
        result = client.native_order(
            out_trade_no=order.order_no,
            description=f"API Capture {order.plan_name or order.plan}会员",
            amount_cents=order.amount_cents,
            attach=f"user_id={user.id};plan={order.plan}",
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"微信支付下单失败：{exc}")
    code_url = result.get("code_url")
    if not code_url:
        raise HTTPException(status_code=502, detail=f"微信支付未返回 code_url：{result}")
    order.code_url = code_url
    order.pay_channel = "wechat_native"
    db.commit()
    db.refresh(order)
    return {"code": 0, "data": {**order_out(order), "reused": reused, "message": "微信支付订单已生成，请在 10 分钟内扫码支付"}}


@router.get("/orders")
def my_orders(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(MembershipOrder).filter(MembershipOrder.user_id == user.id).order_by(MembershipOrder.created_at.desc(), MembershipOrder.id.desc()).limit(50).all()
    for row in rows:
        if row.status == "pending" and row.pay_channel == "wechat_native":
            try:
                sync_wechat_order_status(db, row)
            except Exception:
                pass
    expire_pending_orders(db, user.id)
    rows = db.query(MembershipOrder).filter(MembershipOrder.user_id == user.id).order_by(MembershipOrder.created_at.desc(), MembershipOrder.id.desc()).limit(50).all()
    return {"code": 0, "data": [order_out(x) for x in rows]}


@router.post("/orders/{order_no}/refresh")
def refresh_my_order(order_no: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    order = db.query(MembershipOrder).filter(MembershipOrder.user_id == user.id, MembershipOrder.order_no == order_no).first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.status == "paid":
        return {"code": 0, "message": "订单已支付，会员已开通", "data": order_out(order)}
    if order.status != "pending":
        return {"code": 0, "message": "订单不是待支付状态", "data": order_out(order)}
    order, trade_state = sync_wechat_order_status(db, order)
    message = "订单已支付，会员已自动开通" if order.status == "paid" else f"微信支付状态：{trade_state or '未知/待支付'}"
    return {"code": 0, "message": message, "data": order_out(order), "wechatState": trade_state}


@router.post("/orders/{order_no}/cancel")
def cancel_my_order(order_no: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    expire_pending_orders(db, user.id)
    order = db.query(MembershipOrder).filter(MembershipOrder.user_id == user.id, MembershipOrder.order_no == order_no).first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.status == "paid":
        raise HTTPException(status_code=400, detail="已支付订单不能取消")
    if order.status != "pending":
        return {"code": 0, "message": "订单已取消", "data": order_out(order)}
    close_warning = ""
    if order.pay_channel == "wechat_native" and order.code_url:
        try:
            WechatPayClient(WechatPayConfig.from_settings(settings)).close_order(out_trade_no=order.order_no)
        except Exception as exc:
            # 用户取消以本地状态为准，微信关单失败时给出提示，避免阻塞用户继续创建新订单。
            close_warning = f"；微信关单失败：{exc}"
    order.status = "canceled"
    order.pay_channel = order.pay_channel or "user_cancel"
    db.commit()
    db.refresh(order)
    return {"code": 0, "message": f"订单已取消{close_warning}", "data": order_out(order)}


@router.post("/admin/grant")
def grant_membership(payload: GrantMembershipIn, x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"), db: Session = Depends(get_db)):
    assert_admin_key(x_admin_key)
    if not payload.phone and not payload.user_id:
        raise HTTPException(status_code=400, detail="phone 或 user_id 至少传一个")
    q = db.query(User)
    target = q.filter(User.id == payload.user_id).first() if payload.user_id else q.filter(User.phone == payload.phone).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    activate_membership(target, payload.plan, payload.days)
    db.commit()
    db.refresh(target)
    return {"code": 0, "message": "会员已更新", "data": membership_payload(db, target)}


@router.get("/admin/users")
def admin_users(keyword: str | None = None, page: int = Query(1, ge=1), pageSize: int = Query(20, ge=1, le=100), x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"), db: Session = Depends(get_db)):
    assert_admin_key(x_admin_key)
    q = db.query(User)
    if keyword:
        like = f"%{keyword.strip()}%"
        q = q.filter(or_(User.phone.ilike(like), User.nickname.ilike(like)))
    total = q.count()
    rows = q.order_by(User.created_at.desc(), User.id.desc()).offset((page - 1) * pageSize).limit(pageSize).all()
    data = []
    for u in rows:
        usage = usage_for(db, u)
        data.append({"id": u.id, "phone": mask_phone(u.phone), "nickname": u.nickname, "plan": u.membership_plan, "expiresAt": u.membership_expires_at, "usage": usage, "createdAt": u.created_at})
    return {"code": 0, "data": {"total": total, "list": data}}


@router.get("/admin/orders")
def admin_orders(status: str | None = None, keyword: str | None = None, page: int = Query(1, ge=1), pageSize: int = Query(20, ge=1, le=100), x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"), db: Session = Depends(get_db)):
    assert_admin_key(x_admin_key)
    expire_pending_orders(db)
    q = db.query(MembershipOrder)
    if status:
        q = q.filter(MembershipOrder.status == status)
    if keyword:
        like = f"%{keyword.strip()}%"
        q = q.filter(or_(MembershipOrder.order_no.ilike(like), MembershipOrder.phone.ilike(like)))
    total = q.count()
    rows = q.order_by(MembershipOrder.created_at.desc(), MembershipOrder.id.desc()).offset((page - 1) * pageSize).limit(pageSize).all()
    return {"code": 0, "data": {"total": total, "list": [order_out(x) for x in rows]}}


@router.post("/admin/orders/{order_no}/confirm")
def confirm_order(order_no: str, payload: ConfirmOrderIn | None = None, x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"), db: Session = Depends(get_db)):
    assert_admin_key(x_admin_key)
    order = db.query(MembershipOrder).filter(MembershipOrder.order_no == order_no).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status == "paid":
        return {"code": 0, "message": "订单已支付", "data": order_out(order)}
    expire_pending_orders(db, order.user_id)
    db.refresh(order)
    if order.status != "pending":
        raise HTTPException(status_code=400, detail="订单已超时取消，请让用户重新发起支付")
    user = db.get(User, order.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    order.status = "paid"
    order.pay_channel = (payload.pay_channel if payload else None) or "manual"
    order.paid_at = datetime.now(timezone.utc)
    activate_membership(user, order.plan, order.days)
    db.commit()
    db.refresh(order)
    return {"code": 0, "message": "订单已确认，会员已开通", "data": order_out(order)}


@router.post("/wechat/notify")
async def wechat_notify(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    timestamp = request.headers.get("Wechatpay-Timestamp", "")
    nonce = request.headers.get("Wechatpay-Nonce", "")
    signature = request.headers.get("Wechatpay-Signature", "")
    try:
        client = WechatPayClient(WechatPayConfig.from_settings(settings))
        if not client.verify_notify_signature(timestamp=timestamp, nonce=nonce, body=body, signature=signature):
            raise HTTPException(status_code=401, detail="微信支付回调验签失败")
        payload = await request.json()
        resource = payload.get("resource") or {}
        data = client.decrypt_notify_resource(resource)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"微信支付回调解析失败：{exc}")

    order_no = data.get("out_trade_no")
    trade_state = data.get("trade_state")
    transaction_id = data.get("transaction_id")
    payer_total = int(((data.get("amount") or {}).get("payer_total") or (data.get("amount") or {}).get("total") or 0))
    order = db.query(MembershipOrder).filter(MembershipOrder.order_no == order_no).first()
    if not order:
        return {"code": "FAIL", "message": "订单不存在"}
    if order.status == "paid":
        return {"code": "SUCCESS", "message": "已处理"}
    if order.status != "pending":
        return {"code": "FAIL", "message": "订单不是待支付状态"}
    if trade_state != "SUCCESS":
        return {"code": "SUCCESS", "message": f"忽略非成功支付状态：{trade_state}"}
    if payer_total != int(order.amount_cents):
        return {"code": "FAIL", "message": "支付金额不匹配"}
    try:
        mark_order_paid(db, order, transaction_id=transaction_id)
    except HTTPException:
        return {"code": "FAIL", "message": "用户不存在"}
    return {"code": "SUCCESS", "message": "成功"}
