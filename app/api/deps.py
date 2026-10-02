from fastapi import Depends, HTTPException, Request, WebSocket
from fastapi.security import OAuth2PasswordBearer
from app.core.security import decode_token
from app.services.security import WebSocketTicketService
oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login")
def current_user(request: Request, token: str = Depends(oauth2)) -> dict:
    try:
        payload = decode_token(token)
        if payload.get("type") != "access": raise ValueError
        request.state.user_id = int(payload["sub"])
        return payload
    except ValueError as exc: raise HTTPException(401, "Invalid authentication credentials") from exc


def ensure_admin(user: dict) -> dict:
    """Apply the shared model-management policy to HTTP and WebSocket users."""
    if user.get("role") != "admin": raise HTTPException(403, "Admin role required")
    return user


def require_admin(user=Depends(current_user)):
    return ensure_admin(user)
async def websocket_user(ws: WebSocket, scope: str) -> dict:
    ticket = ws.query_params.get("ticket")
    try:
        service = WebSocketTicketService()
        try: payload = await service.consume(ticket or "", scope)
        finally: await service.close()
        return payload
    except HTTPException:
        await ws.close(code=1008)
        raise
