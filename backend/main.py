import time
from sqlalchemy.exc import OperationalError
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .config import settings
from .database import Base, engine
from .routes.user import router as user_router
from .routes.capture import router as capture_router
from .routes.apis import router as apis_router
from .routes.channel_records import router as channel_records_router
from .routes.rules import router as rules_router
from .routes.labels import router as labels_router
from .routes.label_data import router as label_data_router


def init_db_with_retry(retries: int = 30, delay: float = 1.0) -> None:
    """Docker Compose 中 depends_on 不等于数据库可连接，这里做启动重试。"""
    last_error = None
    for i in range(1, retries + 1):
        try:
            Base.metadata.create_all(bind=engine)
            print(f"Database initialized after {i} attempt(s)")
            return
        except OperationalError as exc:
            last_error = exc
            print(f"Waiting for database... attempt {i}/{retries}")
            time.sleep(delay)
    raise last_error


def ensure_schema_compat() -> None:
    """轻量兼容已有 Docker volume：SQLAlchemy create_all 不会给旧表补列，这里补新增列/索引。"""
    base_statements = [
        "CREATE EXTENSION IF NOT EXISTS pg_trgm",
        "ALTER TABLE capture_sessions ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ",
        "ALTER TABLE capture_sessions ADD COLUMN IF NOT EXISTS ended_at TIMESTAMPTZ",
        "CREATE INDEX IF NOT EXISTS idx_capture_sessions_started_at ON capture_sessions(started_at)",
        "CREATE INDEX IF NOT EXISTS idx_capture_sessions_ended_at ON capture_sessions(ended_at)",
        "ALTER TABLE captured_apis ADD COLUMN IF NOT EXISTS query_params JSONB",
        "ALTER TABLE captured_apis ADD COLUMN IF NOT EXISTS search_keyword TEXT",
        "ALTER TABLE captured_apis ADD COLUMN IF NOT EXISTS matched_rule_id INTEGER",
        "ALTER TABLE captured_apis ADD COLUMN IF NOT EXISTS matched_rule_name VARCHAR(255)",
        "ALTER TABLE captured_apis ADD COLUMN IF NOT EXISTS label_id INTEGER",
        "ALTER TABLE captured_apis ADD COLUMN IF NOT EXISTS label_name VARCHAR(255)",
        "ALTER TABLE captured_apis ADD COLUMN IF NOT EXISTS host VARCHAR(255)",
        "ALTER TABLE captured_apis ADD COLUMN IF NOT EXISTS path TEXT",
        "ALTER TABLE captured_apis ADD COLUMN IF NOT EXISTS content_type VARCHAR(255)",
        "ALTER TABLE captured_apis ADD COLUMN IF NOT EXISTS is_json INTEGER",
        "ALTER TABLE captured_apis ADD COLUMN IF NOT EXISTS response_size INTEGER",
        "ALTER TABLE capture_rules ADD COLUMN IF NOT EXISTS creator_phone VARCHAR(32)",
        "ALTER TABLE capture_rules ADD COLUMN IF NOT EXISTS label_id INTEGER",
        "ALTER TABLE capture_rules ADD COLUMN IF NOT EXISTS label_name VARCHAR(255)",
        "ALTER TABLE channel_product_records ADD COLUMN IF NOT EXISTS label_id INTEGER",
        "ALTER TABLE channel_product_records ADD COLUMN IF NOT EXISTS label_name VARCHAR(255)",
        "CREATE INDEX IF NOT EXISTS idx_captured_apis_host ON captured_apis(host)",
        "CREATE INDEX IF NOT EXISTS idx_captured_apis_search_keyword ON captured_apis USING gin (search_keyword gin_trgm_ops)",
        "CREATE INDEX IF NOT EXISTS idx_captured_apis_matched_rule_id ON captured_apis(matched_rule_id)",
        "CREATE INDEX IF NOT EXISTS idx_captured_apis_label_id ON captured_apis(label_id)",
        "CREATE INDEX IF NOT EXISTS idx_captured_apis_label_name ON captured_apis(label_name)",
        "CREATE INDEX IF NOT EXISTS idx_channel_product_records_user_id ON channel_product_records(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_channel_product_records_session_id ON channel_product_records(session_id)",
        "CREATE INDEX IF NOT EXISTS idx_channel_product_records_api_id ON channel_product_records(api_id)",
        "CREATE INDEX IF NOT EXISTS idx_channel_product_records_label_id ON channel_product_records(label_id)",
        "CREATE INDEX IF NOT EXISTS idx_channel_product_records_label_name ON channel_product_records(label_name)",
        "CREATE INDEX IF NOT EXISTS idx_channel_product_records_sku_id ON channel_product_records(sku_id)",
        "CREATE INDEX IF NOT EXISTS idx_channel_product_records_shop_id ON channel_product_records(shop_id)",
        "CREATE INDEX IF NOT EXISTS idx_channel_product_records_platform ON channel_product_records(platform)",
        "CREATE INDEX IF NOT EXISTS idx_channel_product_records_created_at ON channel_product_records(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_channel_product_records_title ON channel_product_records USING gin (channel_title gin_trgm_ops)",
        "CREATE INDEX IF NOT EXISTS idx_channel_product_records_url ON channel_product_records USING gin (channel_url gin_trgm_ops)",
        "CREATE INDEX IF NOT EXISTS idx_channel_product_records_raw_item ON channel_product_records USING gin (raw_item)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_rule_selection_user_rule ON user_rule_selections(user_id, rule_id)",
        "CREATE INDEX IF NOT EXISTS idx_user_rule_selections_user_id ON user_rule_selections(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_user_rule_selections_rule_id ON user_rule_selections(rule_id)",
        "CREATE INDEX IF NOT EXISTS idx_data_labels_user_id ON data_labels(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_data_labels_name ON data_labels(name)",
        "CREATE INDEX IF NOT EXISTS idx_data_labels_table_name ON data_labels(table_name)",
        "CREATE INDEX IF NOT EXISTS idx_label_data_records_user_id ON label_data_records(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_label_data_records_label_id ON label_data_records(label_id)",
        "CREATE INDEX IF NOT EXISTS idx_label_data_records_rule_id ON label_data_records(rule_id)",
        "CREATE INDEX IF NOT EXISTS idx_label_data_records_row_data ON label_data_records USING gin (row_data)",
    ]
    with engine.begin() as conn:
        for sql in base_statements:
            conn.exec_driver_sql(sql)
        old_table = conn.exec_driver_sql("SELECT to_regclass('public.parsed_apis')").scalar()
        captured_count = conn.exec_driver_sql("SELECT COUNT(*) FROM captured_apis").scalar() or 0
        # 旧 parsed_apis 只允许在 captured_apis 为空的新环境中迁移一次。
        # 否则每次 backend 重启都会把已经清理过的旧未命中脏数据重新插回来。
        if old_table and captured_count == 0:
            conn.exec_driver_sql("""
                INSERT INTO captured_apis (
                  id,user_id,session_id,method,url,request_headers,response_headers,request_params,request_body_raw,
                  response_status,response_body,response_body_text,response_body_raw,duration_ms,page_url,page_title,captured_at,created_at
                )
                SELECT id,user_id,session_id,method,url,request_headers,response_headers,request_params,request_body_raw,
                  response_status,response_body,response_body_text,response_body_raw,duration_ms,page_url,page_title,captured_at,created_at
                FROM parsed_apis
                ON CONFLICT (id) DO NOTHING
            """)
        conn.exec_driver_sql("SELECT setval(pg_get_serial_sequence('captured_apis','id'), COALESCE((SELECT MAX(id) FROM captured_apis), 1), true)")


init_db_with_retry()
ensure_schema_compat()
app = FastAPI(title="API Capture API", description="网页接口捕获、规则解析与数据管理后端 API", version="1.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")] if settings.cors_origins != "*" else ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def limit_upload_size(request: Request, call_next):
    length = request.headers.get("content-length")
    if length and int(length) > settings.max_upload_bytes:
        return JSONResponse({"detail": "Payload too large"}, status_code=413)
    return await call_next(request)

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    from fastapi import HTTPException
    if isinstance(exc, HTTPException):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    return JSONResponse({"detail": "Internal server error"}, status_code=500)

@app.get("/api/health")
def health():
    return {"code": 0, "data": {"ok": True}}

app.include_router(user_router)
app.include_router(capture_router)
app.include_router(apis_router)
app.include_router(channel_records_router)
app.include_router(rules_router)
app.include_router(labels_router)
app.include_router(label_data_router)
