from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import current_user
from app.core.config import get_settings
from app.core.security import create_token, hash_password, verify_password
from app.db.session import get_db
from app.models.database import User
from app.models.schemas import LoginRequest, RegisterRequest, TokenResponse
router = APIRouter(prefix="/auth", tags=["auth"])
def tokens(user: User):
    s = get_settings()
    return TokenResponse(access_token=create_token(str(user.id), user.role, "access", timedelta(minutes=s.access_token_expire_minutes)), refresh_token=create_token(str(user.id), user.role, "refresh", timedelta(days=s.refresh_token_expire_days)))
@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    if await db.scalar(select(User).where(User.email == req.email)): raise HTTPException(409, "Email already registered")
    user = User(email=req.email, password_hash=hash_password(req.password)); db.add(user); await db.commit(); await db.refresh(user); return tokens(user)
@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.email == req.email))
    if not user or not verify_password(req.password, user.password_hash): raise HTTPException(401, "Invalid email or password")
    return tokens(user)
