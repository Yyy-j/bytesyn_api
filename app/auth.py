import os
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from pydantic import BaseModel, Field

from app.db import find_or_create_identity


router = APIRouter(prefix="/auth", tags=["auth"])
bearer_scheme = HTTPBearer(auto_error=False)


class GoogleLoginRequest(BaseModel):
    id_token: str = Field(min_length=1)


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def verify_google_token(token: str) -> dict[str, object]:
    try:
        claims = google_id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            os.environ["GOOGLE_CLIENT_ID"],
        )
    except Exception:
        raise _unauthorized() from None

    subject = claims.get("sub")
    issuer = claims.get("iss")
    if not isinstance(subject, str) or not subject or issuer not in {
        "accounts.google.com",
        "https://accounts.google.com",
    }:
        raise _unauthorized()
    return claims


def create_access_token(user_id: UUID) -> str:
    now = datetime.now(timezone.utc)
    lifetime_minutes = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    claims = {
        "sub": str(user_id),
        "iss": os.environ.get("JWT_ISSUER", "bytesync"),
        "aud": os.environ.get("JWT_AUDIENCE", "bytesync-api"),
        "iat": now,
        "exp": now + timedelta(minutes=lifetime_minutes),
    }
    return jwt.encode(claims, os.environ["JWT_SECRET"], algorithm="HS256")


def get_current_user_id(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
) -> UUID:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    try:
        claims = jwt.decode(
            credentials.credentials,
            os.environ["JWT_SECRET"],
            algorithms=["HS256"],
            issuer=os.environ.get("JWT_ISSUER", "bytesync"),
            audience=os.environ.get("JWT_AUDIENCE", "bytesync-api"),
            options={"require": ["sub", "iss", "aud", "iat", "exp"]},
        )
        return UUID(claims["sub"])
    except Exception:
        raise _unauthorized() from None


@router.post("/google", response_model=AccessTokenResponse)
def google_login(body: GoogleLoginRequest) -> AccessTokenResponse:
    claims = verify_google_token(body.id_token)
    identity = find_or_create_identity(
        provider="google",
        provider_subject=str(claims["sub"]),
        email=claims.get("email") if isinstance(claims.get("email"), str) else None,
    )
    return AccessTokenResponse(access_token=create_access_token(identity["user_id"]))
