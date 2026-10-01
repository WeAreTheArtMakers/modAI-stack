from datetime import timedelta
from app.core.security import create_token, decode_token
def test_token_round_trip():
    token = create_token("1", "user", "access", timedelta(minutes=1))
    assert decode_token(token)["sub"] == "1"
