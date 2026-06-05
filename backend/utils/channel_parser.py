from __future__ import annotations
from typing import Any

# 图中字段 -> 数据库列 -> 常见接口字段别名。只命中明确字段；没有就留空，不做臆造。
FIELD_ALIASES: dict[str, list[str]] = {
    "platform_user": ["平台用户", "platform_user", "platformUser", "user", "userName", "username", "account"],
    "source_user_id": ["用户id", "用户ID", "user_id", "userId", "uid", "sourceUserId"],
    "platform": ["平台", "platform", "sourcePlatform", "site", "mall"],
    "source_created_at": ["创建时间", "created_at", "createdAt", "createTime", "gmtCreate", "time"],
    "search_keyword": ["搜索词", "keyword", "searchKeyword", "search_word", "query", "q"],
    "channel_title": ["渠道标题", "title", "itemTitle", "goodsTitle", "productTitle", "name"],
    "channel_url": ["渠道链接", "url", "itemUrl", "goodsUrl", "productUrl", "link", "detailUrl"],
    "sku_id": ["skuId", "sku_id", "skuid", "sku", "skuID"],
    "price": ["价格", "price", "salePrice", "finalPrice", "couponPrice", "到手价"],
    "sales": ["销量", "sales", "saleCount", "sold", "monthSales", "volume"],
    "channel_image": ["渠道图片", "image", "img", "pic", "picUrl", "imageUrl", "mainImage"],
    "shop_name": ["店铺名称", "shopName", "shop_name", "storeName", "sellerName"],
    "shop_id": ["店铺ID", "shopId", "shop_id", "storeId", "sellerId"],
    "shop_url": ["店铺链接", "shopUrl", "shop_url", "storeUrl", "sellerUrl"],
    "ad_tag": ["广告标签", "adTag", "ad_tag", "promotionTag", "tag"],
    "product_activity": ["商品活动", "productActivity", "activity", "itemActivity", "goodsActivity"],
    "discount_strength": ["优惠力度", "discount", "discountStrength", "coupon", "couponInfo"],
    "platform_category": ["平台细分", "platformCategory", "category", "categoryName", "cidName"],
    "product_info": ["商品信息", "productInfo", "goodsInfo", "itemInfo", "description", "desc"],
    "ranking_info": ["榜单信息", "rankingInfo", "rankInfo", "rank", "ranking"],
    "ship_from": ["发货地", "shipFrom", "sendFrom", "deliveryFrom", "location"],
    "product_marketing": ["商品营销", "productMarketing", "marketing", "itemMarketing"],
    "shop_marketing": ["店铺营销", "shopMarketing", "storeMarketing"],
    "article_number": ["货号", "articleNumber", "article_no", "artNo", "货号"],
    "serial_number": ["序号", "serialNumber", "serial_no", "index", "no"],
    "core_tags": ["核心标签", "coreTags", "core_tags", "tags", "labels"],
    "activity_source": ["活动来源", "activitySource", "activity_source", "source"],
    "channel_page_title": ["频道页标", "频道页标题", "channelPageTitle", "pageTitle"],
    "shop_tags": ["店铺标签", "shopTags", "shop_tags", "storeTags"],
}

LIST_KEYS = [
    "list", "items", "records", "rows", "goodsList", "itemList", "products", "productList",
    "goods", "item", "dataList", "resultList", "searchList", "feeds", "cards", "modules",
    "data", "result",
]
CONTAINER_KEYS = {"data", "result", "payload", "response", "body"}
MIN_FIELD_HITS = 2

def stringify(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return ",".join([stringify(v) or "" for v in value if v is not None]) or None
    return None

def normalized_key(value: Any) -> str:
    return str(value).replace("_", "").replace("-", "").replace(" ", "").lower()

def pick(obj: dict[str, Any], aliases: list[str]) -> str | None:
    for key in aliases:
        if key in obj:
            return stringify(obj.get(key))
    # 兼容大小写/下划线差异，但仍然只在同名 alias 范围内找
    normalized = {normalized_key(k): k for k in obj.keys()}
    for key in aliases:
        real = normalized.get(normalized_key(key))
        if real is not None:
            return stringify(obj.get(real))
    return None

def hit_count(obj: dict[str, Any]) -> int:
    return sum(1 for aliases in FIELD_ALIASES.values() if pick(obj, aliases) is not None)

def looks_like_record(obj: dict[str, Any]) -> bool:
    return hit_count(obj) >= MIN_FIELD_HITS

def find_items(payload: Any, depth: int = 0) -> list[dict[str, Any]]:
    """从响应 JSON 中寻找商品/渠道列表，只返回明确命中字段别名的 dict。

    解析原则：
    1. 只按 FIELD_ALIASES 中的中英文字段名做映射；
    2. 列表里混有非商品对象时会过滤掉；
    3. 找不到明确字段则不落表，避免乱填。
    """
    if depth > 5 or payload is None:
        return []
    if isinstance(payload, list):
        rows = [x for x in payload if isinstance(x, dict) and looks_like_record(x)]
        return rows if rows else []
    if isinstance(payload, dict):
        if looks_like_record(payload):
            return [payload]
        for key in LIST_KEYS:
            if key in payload:
                rows = find_items(payload[key], depth + 1)
                if rows:
                    return rows
        # 先递归常见容器，减少误把统计/配置数组当业务列表。
        for key in CONTAINER_KEYS:
            if key in payload:
                rows = find_items(payload[key], depth + 1)
                if rows:
                    return rows
        for value in payload.values():
            rows = find_items(value, depth + 1)
            if rows:
                return rows
    return []

def map_channel_item(item: dict[str, Any], fallback_search_keyword: str | None = None) -> dict[str, Any]:
    mapped = {column: pick(item, aliases) for column, aliases in FIELD_ALIASES.items()}
    if not mapped.get("search_keyword") and fallback_search_keyword:
        mapped["search_keyword"] = fallback_search_keyword
    mapped["raw_item"] = item
    return mapped

def parse_channel_records(response_body: Any, fallback_search_keyword: str | None = None) -> list[dict[str, Any]]:
    return [map_channel_item(item, fallback_search_keyword) for item in find_items(response_body)]
