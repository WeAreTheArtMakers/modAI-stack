from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.core.config import get_settings
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
def hash_password(password: str) -> str: return pwd_context.hash(password)
def verify_password(password: str, hashed: str) -> bool: return pwd_context.verify(password, hashed)
def create_token(subject: str, role: str, token_type: str, expires: timedelta) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": subject, "role": role, "type": token_type, "iat": now, "exp": now + expires}, get_settings().jwt_secret, algorithm="HS256")
def decode_token(token: str) -> dict:
    try: return jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    except JWTError as exc: raise ValueError("Invalid token") from exc

