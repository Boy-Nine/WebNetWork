from __future__ import annotations
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from ..database import get_db
from ..models import ChannelProductRecord, User
from ..utils.security import get_current_user

router = APIRouter(prefix="/api/channel-records", tags=["channel records"])

COLUMNS = [
    "id", "user_id", "session_id", "api_id", "label_id", "label_name", "platform_user", "source_user_id", "platform", "source_created_at",
    "search_keyword", "channel_title", "channel_url", "sku_id", "price", "sales", "channel_image",
    "shop_name", "shop_id", "shop_url", "ad_tag", "product_activity", "discount_strength", "platform_category",
    "product_info", "ranking_info", "ship_from", "product_marketing", "shop_marketing", "article_number",
    "serial_number", "core_tags", "activity_source", "channel_page_title", "shop_tags", "created_at"
]

def row_to_dict(row: ChannelProductRecord, detail: bool = False):
    data = {col: getattr(row, col) for col in COLUMNS}
    if detail:
        data["raw_item"] = row.raw_item
    return data

FILTERABLE_FIELDS = [
    "platform_user", "source_user_id", "platform", "source_created_at", "search_keyword", "channel_title",
    "channel_url", "sku_id", "price", "sales", "channel_image", "shop_name", "shop_id", "shop_url",
    "ad_tag", "product_activity", "discount_strength", "platform_category", "product_info", "ranking_info",
    "ship_from", "product_marketing", "shop_marketing", "article_number", "serial_number", "core_tags",
    "activity_source", "channel_page_title", "shop_tags",
]

def normalize_dt(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

def apply_filters(q, user: User, keyword: str | None, filters: dict[str, str | None], start_time: datetime | None = None, end_time: datetime | None = None, label_id: int | None = None):
    # 强制用户隔离：所有明细查询、导出、详情都只能看到当前 JWT 用户自己的数据。
    q = q.filter(ChannelProductRecord.user_id == user.id)
    if keyword:
        kw = f"%{keyword.strip()}%"
        q = q.filter(or_(
            ChannelProductRecord.platform_user.ilike(kw),
            ChannelProductRecord.source_user_id.ilike(kw),
            ChannelProductRecord.platform.ilike(kw),
            ChannelProductRecord.search_keyword.ilike(kw),
            ChannelProductRecord.channel_title.ilike(kw),
            ChannelProductRecord.channel_url.ilike(kw),
            ChannelProductRecord.sku_id.ilike(kw),
            ChannelProductRecord.shop_name.ilike(kw),
            ChannelProductRecord.shop_id.ilike(kw),
            ChannelProductRecord.article_number.ilike(kw),
        ))
    if start_time:
        q = q.filter(ChannelProductRecord.created_at >= start_time)
    if end_time:
        q = q.filter(ChannelProductRecord.created_at <= end_time)
    if label_id is not None:
        q = q.filter(ChannelProductRecord.label_id == label_id)
    for field, value in filters.items():
        if value is None or value == "":
            continue
        column = getattr(ChannelProductRecord, field, None)
        if column is not None:
            q = q.filter(column.ilike(f"%{value.strip()}%"))
    return q

def collect_filters(**kwargs) -> dict[str, str | None]:
    return {key: value for key, value in kwargs.items() if key in FILTERABLE_FIELDS}

@router.get("/list")
def list_channel_records(
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    startTime: datetime | None = None,
    endTime: datetime | None = None,
    labelId: int | None = None,
    keyword: str | None = None,
    skuId: str | None = None,
    shopId: str | None = None,
    platformUser: str | None = None,
    sourceUserId: str | None = None,
    platform: str | None = None,
    sourceCreatedAt: str | None = None,
    searchKeyword: str | None = None,
    channelTitle: str | None = None,
    channelUrl: str | None = None,
    price: str | None = None,
    sales: str | None = None,
    channelImage: str | None = None,
    shopName: str | None = None,
    shopUrl: str | None = None,
    adTag: str | None = None,
    productActivity: str | None = None,
    discountStrength: str | None = None,
    platformCategory: str | None = None,
    productInfo: str | None = None,
    rankingInfo: str | None = None,
    shipFrom: str | None = None,
    productMarketing: str | None = None,
    shopMarketing: str | None = None,
    articleNumber: str | None = None,
    serialNumber: str | None = None,
    coreTags: str | None = None,
    activitySource: str | None = None,
    channelPageTitle: str | None = None,
    shopTags: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    filters = collect_filters(
        platform_user=platformUser, source_user_id=sourceUserId, platform=platform, source_created_at=sourceCreatedAt,
        search_keyword=searchKeyword, channel_title=channelTitle, channel_url=channelUrl, sku_id=skuId,
        price=price, sales=sales, channel_image=channelImage, shop_name=shopName, shop_id=shopId, shop_url=shopUrl,
        ad_tag=adTag, product_activity=productActivity, discount_strength=discountStrength, platform_category=platformCategory,
        product_info=productInfo, ranking_info=rankingInfo, ship_from=shipFrom, product_marketing=productMarketing,
        shop_marketing=shopMarketing, article_number=articleNumber, serial_number=serialNumber, core_tags=coreTags,
        activity_source=activitySource, channel_page_title=channelPageTitle, shop_tags=shopTags,
    )
    base = apply_filters(db.query(ChannelProductRecord), user, keyword, filters, normalize_dt(startTime), normalize_dt(endTime), labelId)
    total = base.count()
    rows = base.order_by(ChannelProductRecord.created_at.desc(), ChannelProductRecord.id.desc()).offset((page - 1) * pageSize).limit(pageSize).all()
    return {"code": 0, "data": {"total": total, "list": [row_to_dict(r) for r in rows]}}

@router.get("/export")
def export_channel_records(
    startTime: datetime | None = None,
    endTime: datetime | None = None,
    labelId: int | None = None,
    keyword: str | None = None,
    skuId: str | None = None,
    shopId: str | None = None,
    platformUser: str | None = None,
    sourceUserId: str | None = None,
    platform: str | None = None,
    sourceCreatedAt: str | None = None,
    searchKeyword: str | None = None,
    channelTitle: str | None = None,
    channelUrl: str | None = None,
    price: str | None = None,
    sales: str | None = None,
    channelImage: str | None = None,
    shopName: str | None = None,
    shopUrl: str | None = None,
    adTag: str | None = None,
    productActivity: str | None = None,
    discountStrength: str | None = None,
    platformCategory: str | None = None,
    productInfo: str | None = None,
    rankingInfo: str | None = None,
    shipFrom: str | None = None,
    productMarketing: str | None = None,
    shopMarketing: str | None = None,
    articleNumber: str | None = None,
    serialNumber: str | None = None,
    coreTags: str | None = None,
    activitySource: str | None = None,
    channelPageTitle: str | None = None,
    shopTags: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    filters = collect_filters(
        platform_user=platformUser, source_user_id=sourceUserId, platform=platform, source_created_at=sourceCreatedAt,
        search_keyword=searchKeyword, channel_title=channelTitle, channel_url=channelUrl, sku_id=skuId,
        price=price, sales=sales, channel_image=channelImage, shop_name=shopName, shop_id=shopId, shop_url=shopUrl,
        ad_tag=adTag, product_activity=productActivity, discount_strength=discountStrength, platform_category=platformCategory,
        product_info=productInfo, ranking_info=rankingInfo, ship_from=shipFrom, product_marketing=productMarketing,
        shop_marketing=shopMarketing, article_number=articleNumber, serial_number=serialNumber, core_tags=coreTags,
        activity_source=activitySource, channel_page_title=channelPageTitle, shop_tags=shopTags,
    )
    rows = apply_filters(db.query(ChannelProductRecord), user, keyword, filters, normalize_dt(startTime), normalize_dt(endTime), labelId).order_by(ChannelProductRecord.created_at.desc(), ChannelProductRecord.id.desc()).limit(20000).all()
    return {"code": 0, "data": [row_to_dict(r, detail=True) for r in rows]}

@router.get("/{record_id}")
def detail_channel_record(record_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.query(ChannelProductRecord).filter(and_(ChannelProductRecord.id == record_id, ChannelProductRecord.user_id == user.id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Channel record not found")
    return row_to_dict(row, detail=True)
