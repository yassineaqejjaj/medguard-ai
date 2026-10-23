import uuid
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .db import sessionmaker, set_tenant
from .models import User
from . import ratelimit

ROLES = ("viewer", "reviewer", "engineer", "admin")  # ascending privilege for hierarchy checks
_bearer = HTTPBearer(auto_error=False)
_jwks: PyJWKClient | None = None


@dataclass
class Principal:
    user_id: uuid.UUID
    org_id: uuid.UUID
    role: str
    email: str
    session: AsyncSession


def _signing_key(token: str):
    global _jwks
    s = get_settings()
    if _jwks is None:
        _jwks = PyJWKClient(s.oidc_jwks_url or f"{s.oidc_issuer}/protocol/openid-connect/certs", cache_keys=True)
    return _jwks.get_signing_key_from_jwt(token).key


def decode_token(token: str) -> dict:
    s = get_settings()
    try:
        return jwt.decode(token, _signing_key(token), algorithms=["RS256", "ES256"], audience=s.oidc_audience,
                          issuer=s.oidc_issuer, options={"require": ["exp", "iss", "sub"]})
    except jwt.PyJWTError as e:
        raise HTTPException(401, "Invalid or expired token") from e


def role_from_claims(claims: dict) -> str | None:
    roles = set(claims.get("realm_access", {}).get("roles", []))
    for r in reversed(ROLES):  # most privileged wins
        if r in roles:
            return r
    return None


async def principal(request: Request, cred: HTTPAuthorizationCredentials | None = Depends(_bearer)):
    """Authenticates, resolves the tenant from the token (never from client input),
    binds the DB transaction to it, and provisions the user row on first login."""
    if cred is None:
        raise HTTPException(401, "Missing bearer token")
    claims = decode_token(cred.credentials)
    role = role_from_claims(claims)
    slug = claims.get(get_settings().org_claim)
    if not role or not slug:
        raise HTTPException(403, "Token carries no MedGuard role or organisation")

    async with sessionmaker()() as session:
        async with session.begin():
            org_id = (await session.execute(text("SELECT org_id_by_slug(:s)"), {"s": slug})).scalar_one_or_none()
            if org_id is None:
                raise HTTPException(403, "Unknown organisation")
            await set_tenant(session, org_id)
            user = (await session.execute(select(User).where(User.oidc_sub == claims["sub"]))).scalar_one_or_none()
            if user is None:
                user = User(org_id=org_id, oidc_sub=claims["sub"], email=claims.get("email", ""),
                            display_name=claims.get("name", ""), role=role)
                session.add(user)
                await session.flush()
            elif user.role != role:  # IdP is the source of truth for roles
                user.role = role
            if not user.active:
                raise HTTPException(403, "User deactivated")
            await ratelimit.check(f"user:{user.id}")
            yield Principal(user.id, org_id, role, user.email, session)


def require(min_role: str):
    need = ROLES.index(min_role)

    async def dep(p: Principal = Depends(principal)) -> Principal:
        if ROLES.index(p.role) < need:
            raise HTTPException(403, f"Requires role {min_role} or higher")
        return p

    return dep


def require_roles(*allowed: str):
    """Exact-role gate for duties that must not be inherited by engineers (e.g. medical validation)."""

    async def dep(p: Principal = Depends(principal)) -> Principal:
        if p.role not in allowed:
            raise HTTPException(403, f"Requires one of: {', '.join(allowed)}")
        return p

    return dep
