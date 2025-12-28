import os
import time

import jwt

_DEFAULT_TTL_SECONDS = 30 * 24 * 60 * 60
_WARNED_MISSING_SECRET = False


class JwtError(Exception):
    pass


def get_jwt_secret():
    global _WARNED_MISSING_SECRET
    secret = os.environ.get("FISHTEST_JWT_SECRET", "")
    if not secret and not _WARNED_MISSING_SECRET:
        _WARNED_MISSING_SECRET = True
        print(
            "FISHTEST_JWT_SECRET is missing, using an insecure default for worker tokens.",
            flush=True,
        )
    return secret or "fishtest-insecure-jwt"


def create_token(username, ttl_seconds=_DEFAULT_TTL_SECONDS, now=None):
    if now is None:
        now = int(time.time())
    payload = {"sub": username, "iat": now, "exp": now + ttl_seconds}
    return jwt.encode(payload, get_jwt_secret(), algorithm="HS256")


def decode_token(token):
    try:
        return jwt.decode(
            token,
            get_jwt_secret(),
            algorithms=["HS256"],
            options={"require": ["exp", "sub", "iat"]},
        )
    except jwt.ExpiredSignatureError:
        raise JwtError("Token expired")
    except jwt.InvalidTokenError as e:
        raise JwtError("Invalid token") from e
