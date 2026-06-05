from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User
from ..schemas import RegisterOut, TokenOut, UserCreate, UserLogin
from ..utils.security import create_token, hash_password, verify_password, get_current_user

router = APIRouter(prefix="/api/user", tags=["user"])

def token_response(user: User, message: str = "登录成功") -> dict:
    return {"code": 0, "message": message, "token": create_token(user), "userId": user.id, "phone": user.phone, "user": user}

@router.post("/register", response_model=RegisterOut)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.phone == payload.phone).first():
        raise HTTPException(status_code=409, detail="Phone already registered")
    user = User(phone=payload.phone, password_hash=hash_password(payload.password), nickname=payload.phone)
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"code": 0, "message": "注册成功", "userId": user.id}

@router.post("/login", response_model=TokenOut)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.phone == payload.phone).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid phone or password")
    return token_response(user)

@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"code": 0, "data": {"id": user.id, "phone": user.phone, "nickname": user.nickname}}
