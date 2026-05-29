"""OIDC client for bcse-id (id.bcse-vju.com).

bcse-id is a custom OIDC IdP using HS256 with a shared secret (not RS256/JWKS).
Endpoints — paths are non-standard:
  - GET  /authorize            user-facing
  - POST /api/oidc/token       server-to-server, HTTP Basic auth
  - GET  /api/oidc/userinfo    optional Identity lookup

Integration pattern follows docs/OIDC-CLIENT-INTEGRATION.md §4 in the
bcse-internship-careerpath repo. SV14 is the first FastAPI client in the
ecosystem — SV02 (AI Advisor) can copy this when it onboards.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from typing import Any
from urllib.parse import urlencode

import httpx
from jose import JWTError, jwt
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import User, UserRole
from app.models.quota import UserQuota


# ── Role mapping ───────────────────────────────────────────────────────
# bcse-id IdentityRole → SV14 UserRole. Director maps to ADMIN because the
# Giám đốc CT BCSE is the platform owner. External users are rejected —
# SV14 is internal-only (no DN customers like SV09 has).
_ROLE_MAP: dict[str, UserRole] = {
    "student": UserRole.STUDENT,
    "lecturer": UserRole.LECTURER,
    "director": UserRole.ADMIN,
    "staff": UserRole.TA,
    "alumni": UserRole.STUDENT,
}


class SsoError(Exception):
    """SSO flow failures — surfaced as redirects to /login?error=... by routes."""


def map_bcse_role(bcse_role: str | None, app_role: str | None) -> UserRole:
    """app_role claim (per-app override) wins, otherwise default role mapping."""
    if app_role:
        # If admin set a fine-grained role on bcse-id AppAccess, honor it when
        # it matches a SV14 UserRole. Otherwise fall through to default map.
        try:
            return UserRole(app_role)
        except ValueError:
            pass
    if not bcse_role:
        raise SsoError("missing role claim from bcse-id")
    mapped = _ROLE_MAP.get(bcse_role.lower())
    if mapped is None:
        raise SsoError(f"unsupported bcse-id role: {bcse_role}")
    return mapped


# ── OIDC flow ──────────────────────────────────────────────────────────

def _redirect_uri() -> str:
    s = get_settings()
    return f"{s.BCSE_ID_APP_URL.rstrip('/')}/api/auth/sso/callback"


def build_authorize_url(state: str) -> str:
    s = get_settings()
    params = {
        "client_id": s.BCSE_ID_CLIENT_ID,
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": "openid profile email",
        "state": state,
    }
    return f"{s.BCSE_ID_ISSUER.rstrip('/')}/authorize?{urlencode(params)}"


async def exchange_code(code: str) -> dict[str, Any]:
    """Exchange auth code for an id_token, verify HS256 signature, return claims."""
    s = get_settings()
    client_id = s.BCSE_ID_CLIENT_ID
    client_secret = s.BCSE_ID_CLIENT_SECRET.get_secret_value()
    creds = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

    token_url = f"{s.BCSE_ID_ISSUER.rstrip('/')}/api/oidc/token"
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": _redirect_uri(),
            },
            headers={"authorization": f"Basic {creds}"},
        )
    if r.status_code != 200:
        logger.error(
            "bcse-id token exchange failed",
            status=r.status_code,
            body=r.text[:300],
        )
        raise SsoError(f"token exchange {r.status_code}")
    id_token = r.json().get("id_token")
    if not id_token:
        raise SsoError("token response missing id_token")

    try:
        claims = jwt.decode(
            id_token,
            s.BCSE_ID_JWT_SECRET.get_secret_value(),
            algorithms=["HS256"],
            issuer=s.BCSE_ID_ISSUER.rstrip("/"),
            audience=client_id,
        )
    except JWTError as e:
        raise SsoError(f"id_token verify failed: {e}") from e
    return claims


# ── User upsert ────────────────────────────────────────────────────────

async def upsert_user_from_claims(db: AsyncSession, claims: dict[str, Any]) -> User:
    """Link bcse-id identity to a local User row.

    Resolution order:
      1. Match by oidc_subject (already linked) → update + return.
      2. Match by email (legacy local account) → lazy-link, return.
      3. Lazy-provision new User from claims (admin-domain emails only — bcse-id
         already gates external/non-VJU at the IdP layer).
    """
    sub = claims.get("sub")
    email = (claims.get("email") or "").lower().strip()
    name = claims.get("name") or email.split("@")[0]
    bcse_role = claims.get("role")
    app_role = claims.get("app_role")
    student_code = claims.get("vjuId") or claims.get("studentCode")

    if not sub or not email:
        raise SsoError("id_token missing sub or email")

    role = map_bcse_role(bcse_role, app_role)

    # 1. Match by oidc_subject
    user = (
        await db.execute(select(User).where(User.oidc_subject == sub))
    ).scalar_one_or_none()
    if user is not None:
        if not user.is_active:
            raise SsoError("user account is inactive")
        user.email = email
        user.full_name = name
        if user.role != role:
            user.role = role
        if student_code and user.student_code != student_code:
            user.student_code = student_code
        return user

    # 2. Match by email — lazy-link
    user = (
        await db.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if user is not None:
        if not user.is_active:
            raise SsoError("user account is inactive")
        user.oidc_subject = sub
        user.full_name = name
        user.role = role
        if student_code:
            user.student_code = student_code
        # Stop forcing password change once linked via SSO — they have a real identity now.
        user.must_change_password = False
        return user

    # 3. Lazy-provision
    user = User(
        email=email,
        full_name=name,
        role=role,
        oidc_subject=sub,
        student_code=student_code,
        password_hash=None,
        must_change_password=False,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    db.add(UserQuota(user_id=user.id))
    return user


# ── State cookie helpers (CSRF) ─────────────────────────────────────────

def gen_state() -> str:
    return secrets.token_urlsafe(32)


def encode_state_cookie(state: str, return_to: str) -> str:
    return json.dumps({"state": state, "returnTo": return_to})


def decode_state_cookie(raw: str | None) -> tuple[str, str] | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data["state"], data.get("returnTo", "/")
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


# ── Webhook signature verification ─────────────────────────────────────

def verify_webhook_signature(body: bytes, signature_header: str | None) -> bool:
    """HMAC-SHA256 — bcse-id sends `x-bcse-id-signature: sha256=<hex>`."""
    if not signature_header:
        return False
    s = get_settings()
    secret = s.BCSE_ID_WEBHOOK_SECRET.get_secret_value().encode()
    expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
    # Allow both "sha256=<hex>" and bare "<hex>" forms
    received = signature_header.removeprefix("sha256=").strip()
    return hmac.compare_digest(expected, received)
