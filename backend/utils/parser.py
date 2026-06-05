def parse_capture(xhr_list: list[dict]) -> dict:
    """预留解析入口：后续可在这里提取指定 API 字段、脱敏、检测敏感信息等。"""
    statuses = []
    for item in xhr_list:
        status = item.get("responseStatus", item.get("status"))
        if status is not None:
            statuses.append(status)
    return {
        "xhr_count": len(xhr_list),
        "status_counts": {str(s): statuses.count(s) for s in sorted(set(statuses))},
        "urls": [x.get("url") for x in xhr_list[:50]],
    }
