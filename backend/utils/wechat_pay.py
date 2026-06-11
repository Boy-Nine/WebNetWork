from __future__ import annotations
import base64
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _read_text_or_file(value: str | None, path: str | None) -> str:
    if value:
        return value.replace('\\n', '\n')
    if path:
        return Path(path).read_text()
    raise ValueError('missing key/cert config')


def cert_serial_no(cert_path: str) -> str:
    cert = x509.load_pem_x509_certificate(Path(cert_path).read_bytes())
    return format(cert.serial_number, 'X').upper()


@dataclass
class WechatPayConfig:
    enabled: bool
    appid: str
    mchid: str
    api_v3_key: str
    notify_url: str
    private_key_path: str
    cert_path: str
    serial_no: str
    platform_cert_path: str | None = None
    verify_notify_signature: bool = False

    @classmethod
    def from_settings(cls, settings: Any) -> 'WechatPayConfig':
        cert_path = settings.wechat_pay_cert_path
        serial_no = settings.wechat_pay_mch_serial_no or (cert_serial_no(cert_path) if cert_path and Path(cert_path).exists() else '')
        return cls(
            enabled=bool(settings.wechat_pay_enabled),
            appid=settings.wechat_pay_app_id,
            mchid=settings.wechat_pay_merchant_id,
            api_v3_key=settings.wechat_pay_api_key_v3,
            notify_url=settings.wechat_pay_notify_url,
            private_key_path=settings.wechat_pay_key_path,
            cert_path=cert_path,
            serial_no=serial_no,
            platform_cert_path=settings.wechat_pay_platform_cert_path or None,
            verify_notify_signature=bool(settings.wechat_pay_verify_notify_signature),
        )

    def validate(self) -> None:
        missing = []
        for key in ['appid', 'mchid', 'api_v3_key', 'notify_url', 'private_key_path', 'cert_path', 'serial_no']:
            if not getattr(self, key):
                missing.append(key)
        if missing:
            raise ValueError(f'微信支付配置缺失: {", ".join(missing)}')
        if len(self.api_v3_key.encode()) != 32:
            raise ValueError('WECHAT_PAY_API_KEY_V3 必须是 32 字节')
        if not Path(self.private_key_path).exists():
            raise ValueError(f'商户私钥不存在: {self.private_key_path}')
        if not Path(self.cert_path).exists():
            raise ValueError(f'商户证书不存在: {self.cert_path}')
        if self.verify_notify_signature and (not self.platform_cert_path or not Path(self.platform_cert_path).exists()):
            raise ValueError('开启回调验签时必须配置 WECHAT_PAY_PLATFORM_CERT_PATH')


class WechatPayClient:
    def __init__(self, config: WechatPayConfig):
        self.config = config
        self.config.validate()
        self._private_key = serialization.load_pem_private_key(Path(config.private_key_path).read_bytes(), password=None)

    def _sign(self, message: str) -> str:
        signature = self._private_key.sign(message.encode('utf-8'), padding.PKCS1v15(), hashes.SHA256())
        return base64.b64encode(signature).decode('utf-8')

    def _authorization(self, method: str, url_path_with_query: str, body: str, nonce: str, timestamp: str) -> str:
        message = f'{method}\n{url_path_with_query}\n{timestamp}\n{nonce}\n{body}\n'
        signature = self._sign(message)
        return (
            'WECHATPAY2-SHA256-RSA2048 '
            f'mchid="{self.config.mchid}",nonce_str="{nonce}",signature="{signature}",'
            f'timestamp="{timestamp}",serial_no="{self.config.serial_no}"'
        )

    def native_order(self, *, out_trade_no: str, description: str, amount_cents: int, attach: str = '') -> dict[str, Any]:
        body_obj = {
            'appid': self.config.appid,
            'mchid': self.config.mchid,
            'description': description[:127],
            'out_trade_no': out_trade_no,
            'notify_url': self.config.notify_url,
            'amount': {'total': int(amount_cents), 'currency': 'CNY'},
        }
        if attach:
            body_obj['attach'] = attach[:128]
        body = json.dumps(body_obj, ensure_ascii=False, separators=(',', ':'))
        path = '/v3/pay/transactions/native'
        nonce = base64.urlsafe_b64encode(os.urandom(18)).decode().rstrip('=')
        timestamp = str(int(time.time()))
        req = urllib.request.Request(
            'https://api.mch.weixin.qq.com' + path,
            data=body.encode('utf-8'),
            method='POST',
            headers={
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Authorization': self._authorization('POST', path, body, nonce, timestamp),
                'User-Agent': 'ChromeNetWork/1.0',
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode('utf-8') or '{}')
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode('utf-8', errors='replace')
            raise RuntimeError(f'微信支付下单失败 HTTP {exc.code}: {detail}') from exc

    def query_order(self, *, out_trade_no: str) -> dict[str, Any]:
        path = f'/v3/pay/transactions/out-trade-no/{out_trade_no}?mchid={self.config.mchid}'
        nonce = base64.urlsafe_b64encode(os.urandom(18)).decode().rstrip('=')
        timestamp = str(int(time.time()))
        req = urllib.request.Request(
            'https://api.mch.weixin.qq.com' + path,
            method='GET',
            headers={
                'Accept': 'application/json',
                'Authorization': self._authorization('GET', path, '', nonce, timestamp),
                'User-Agent': 'ChromeNetWork/1.0',
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode('utf-8') or '{}')
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode('utf-8', errors='replace')
            raise RuntimeError(f'微信支付查单失败 HTTP {exc.code}: {detail}') from exc

    def close_order(self, *, out_trade_no: str) -> None:
        body_obj = {'mchid': self.config.mchid}
        body = json.dumps(body_obj, ensure_ascii=False, separators=(',', ':'))
        path = f'/v3/pay/transactions/out-trade-no/{out_trade_no}/close'
        nonce = base64.urlsafe_b64encode(os.urandom(18)).decode().rstrip('=')
        timestamp = str(int(time.time()))
        req = urllib.request.Request(
            'https://api.mch.weixin.qq.com' + path,
            data=body.encode('utf-8'),
            method='POST',
            headers={
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Authorization': self._authorization('POST', path, body, nonce, timestamp),
                'User-Agent': 'ChromeNetWork/1.0',
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status not in (200, 204):
                    detail = resp.read().decode('utf-8', errors='replace')
                    raise RuntimeError(f'微信支付关单失败 HTTP {resp.status}: {detail}')
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode('utf-8', errors='replace')
            # 订单不存在或已关闭时，本地取消可视作幂等成功。
            if exc.code in (400, 404) and any(code in detail for code in ('ORDERNOTEXIST', 'ORDER_CLOSED', 'ORDER_CLOSED_BY_MCH')):
                return
            raise RuntimeError(f'微信支付关单失败 HTTP {exc.code}: {detail}') from exc

    def decrypt_notify_resource(self, resource: dict[str, Any]) -> dict[str, Any]:
        aad = (resource.get('associated_data') or '').encode('utf-8')
        nonce = (resource.get('nonce') or '').encode('utf-8')
        ciphertext = base64.b64decode(resource.get('ciphertext') or '')
        aesgcm = AESGCM(self.config.api_v3_key.encode('utf-8'))
        plaintext = aesgcm.decrypt(nonce, ciphertext, aad)
        return json.loads(plaintext.decode('utf-8'))

    def verify_notify_signature(self, *, timestamp: str, nonce: str, body: bytes, signature: str) -> bool:
        if not self.config.verify_notify_signature:
            return True
        if not self.config.platform_cert_path:
            return False
        cert = x509.load_pem_x509_certificate(Path(self.config.platform_cert_path).read_bytes())
        public_key = cert.public_key()
        message = f'{timestamp}\n{nonce}\n{body.decode("utf-8")}\n'.encode('utf-8')
        try:
            public_key.verify(base64.b64decode(signature), message, padding.PKCS1v15(), hashes.SHA256())
            return True
        except Exception:
            return False
