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
    # 管理员手动开通/续期会员接口密钥；生产环境必须通过环境变量覆盖。
    membership_admin_key: str = "change-me-membership-admin-key"

    # 微信支付 API v3 / Native 扫码支付。上线前通常只需要改 notify_url 为公网 HTTPS 地址。
    wechat_pay_enabled: bool = False
    wechat_pay_merchant_id: str = ""
    wechat_pay_api_key_v3: str = ""
    wechat_pay_app_id: str = ""
    wechat_pay_notify_url: str = "http://localhost:3088/api/membership/wechat/notify"
    wechat_pay_cert_path: str = "/app/backend/certs/apiclient_cert.pem"
    wechat_pay_key_path: str = "/app/backend/certs/apiclient_key.pem"
    # 可不填：为空时启动时从 apiclient_cert.pem 自动读取。
    wechat_pay_mch_serial_no: str = ""
    # 生产强烈建议配置微信支付平台证书并开启验签。未配置时仍会解密回调并校验订单号/金额。
    wechat_pay_platform_cert_path: str = ""
    wechat_pay_verify_notify_signature: bool = False

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
