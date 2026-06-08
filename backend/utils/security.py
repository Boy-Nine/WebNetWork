from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from ..config import settings
from ..database import get_db
from ..models import User

# bcrypt_sha256 先 SHA256 预处理，可规避 bcrypt 72 bytes 限制；保留 bcrypt 兼容旧数据。
pwd_context = CryptContext(schemes=["bcrypt_sha256", "bcrypt"], deprecated="auto")
bearer = HTTPBearer()

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)

def create_token(user: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(user.id), "phone": user.phone, "exp": exp, "iat": datetime.now(timezone.utc)}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

def get_current_user(creds: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)) -> User:
    try:
        payload = jwt.decode(creds.credentials, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def mask_phone(value: str | None) -> str | None:
    """Return a display-safe phone value for API responses."""
    if value is None:
        return None
    text = str(value)
    digits = ''.join(ch for ch in text if ch.isdigit())
    if len(digits) < 7:
        return text
    # Preserve common +country prefix only visually through the original first chars.
    return f"{text[:3]}****{text[-4:]}"

SENSITIVE_PHONE_KEYS = {"phone", "手机号", "手机", "联系电话", "联系方式", "mobile", "tel", "telephone", "creator_phone"}

def mask_sensitive_payload(value):
    """Recursively mask obvious phone fields in JSON payloads before returning to clients."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if str(k).lower() in SENSITIVE_PHONE_KEYS or str(k) in SENSITIVE_PHONE_KEYS:
                out[k] = mask_phone(v) if v is not None else v
            else:
                out[k] = mask_sensitive_payload(v)
        return out
    if isinstance(value, list):
        return [mask_sensitive_payload(v) for v in value]
    return value
