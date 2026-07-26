"""
app/api/deps.py

FastAPI dependencies, particularly for authentication and database sessions.
Uses JWKS-based verification (RS256) compatible with Supabase's new JWT signing keys.
No SUPABASE_JWT_SECRET needed.
"""

from collections.abc import AsyncGenerator
from typing import Annotated

import httpx
import jwt
from jwt import PyJWKClient
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.database import get_db
from app.db.models import User
from app.repositories.user_repo import UserRepository

# Re-export get_db for convenience
__all__ = ["get_db", "get_current_user", "DbSession"]

security = HTTPBearer()

DbSession = Annotated[AsyncSession, Depends(get_db)]

# PyJWKClient caches the JWKS keys in memory and refreshes automatically
# Supabase JWKS endpoint: https://<project>.supabase.co/auth/v1/.well-known/jwks.json
_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        jwks_uri = f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        _jwks_client = PyJWKClient(jwks_uri, cache_keys=True)
    return _jwks_client


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: DbSession,
) -> User:
    """
    Validates the Supabase JWT using the JWKS endpoint (RS256).
    Falls back to HS256 with SUPABASE_JWT_SECRET if configured (legacy projects).
    """
    token = credentials.credentials

    try:
        # Try JWKS-based verification first (new Supabase JWT signing keys)
        jwks_client = _get_jwks_client()
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            options={"verify_aud": False},
        )
    except Exception as jwks_error:
        # Fall back to HS256 with shared secret (legacy Supabase projects)
        secret = getattr(settings, "supabase_jwt_secret", None)
        if not secret:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from jwks_error
        try:
            payload = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                options={"verify_aud": False},
            )
        except jwt.ExpiredSignatureError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        except jwt.InvalidTokenError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

    # The subject ('sub') of a Supabase JWT is the user's UUID
    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload: missing subject.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    email = payload.get("email") or ""
    user_metadata = payload.get("user_metadata", {})
    full_name = user_metadata.get("full_name") or payload.get("name") or ""

    # Upsert the user in our public.users table
    user_repo = UserRepository(db)
    try:
        user = await user_repo.upsert_user(
            user_id=user_id_str,
            email=email,
            full_name=full_name,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create user record: {exc}",
        ) from exc

    return user

    """
    Validates the Supabase JWT token and returns the current user.
    If the user doesn't exist in our public.users table yet, it upserts them.
    """
    token = credentials.credentials
    secret = settings.supabase_jwt_secret

    if not secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Supabase JWT secret is not configured.",
        )

    try:
        # Supabase signs tokens with HS256 and the JWT secret found in settings
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={"verify_aud": False},  # Audience verification often not strictly needed here, or can be set to 'authenticated'
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    # The subject ('sub') of a Supabase JWT is the user's UUID
    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload: missing subject.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    email = payload.get("email") or ""
    # Sometimes names are in user_metadata
    user_metadata = payload.get("user_metadata", {})
    full_name = user_metadata.get("full_name") or payload.get("name") or ""

    # Upsert the user in our public.users table using UserRepository
    user_repo = UserRepository(db)
    try:
        user = await user_repo.upsert_user(
            user_id=user_id_str,
            email=email,
            full_name=full_name,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create user record: {exc}",
        ) from exc

    return user
