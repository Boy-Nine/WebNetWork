from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://webgrabber:webgrabber@db:5432/webgrabber"
    jwt_secret_key: str = "change-me-in-production-change-me-32bytes"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080
    max_upload_bytes: int = 12 * 1024 * 1024
    max_html_size_mb: int = 5
    max_response_body_mb: int = 2
    max_xhr_items: int = 200
    # 逗号分隔；* 表示允许任意 origin。当前项目不用 cookie，allow_credentials=False，* 更适合插件调试。
    cors_origins: str = "*"

    @property
    def max_html_bytes(self) -> int:
        return self.max_html_size_mb * 1024 * 1024

    @property
    def max_response_body_bytes(self) -> int:
        return self.max_response_body_mb * 1024 * 1024

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
