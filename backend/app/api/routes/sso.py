"""SSO routes — bcse-id (id.bcse-vju.com) OIDC client + webhook receiver.

  GET  /api/auth/sso/authorize?returnTo=…  → set state cookie + 302 to IdP
  GET  /api/auth/sso/callback?code=…&state=…  → exchange code, issue local session
  POST /api/webhooks/bcse-id               → identity.{status_changed,updated} events
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import issue_access_token, issue_refresh_token, set_auth_cookies
from app.models import User
from app.services import sso_bcse_id as sso
from app.services.audit import audit_log

router = APIRouter(prefix="/auth/sso", tags=["sso"])
webhook_router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# State cookie — scoped to /api/auth so it travels through both /authorize and /callback.
STATE_COOKIE = "lab_sso_state"
STATE_COOKIE_PATH = "/api/auth"
STATE_TTL_SECONDS = 600  # 10 minutes — matches OIDC code TTL on bcse-id side


@router.get("/authorize")
async def sso_authorize(returnTo: str = "/") -> Response:
    s = get_settings()
    if not s.BCSE_ID_ISSUER:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "SSO_NOT_CONFIGURED"},
        )
    state = sso.gen_state()
    resp = RedirectResponse(sso.build_authorize_url(state), status_code=302)
    resp.set_cookie(
        STATE_COOKIE,
        value=sso.encode_state_cookie(state, returnTo),
        max_age=STATE_TTL_SECONDS,
        httponly=True,
        secure=s.is_prod,
        samesite="lax",
        path=STATE_COOKIE_PATH,
    )
    return resp


@router.get("/callback")
async def sso_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    lab_sso_state: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> Response:
    s = get_settings()
    frontend = s.BCSE_ID_APP_URL.rstrip("/")

    def fail(reason: str) -> Response:
        r = RedirectResponse(f"{frontend}/login?error={reason}", status_code=302)
        r.delete_cookie(STATE_COOKIE, path=STATE_COOKIE_PATH)
        return r

    if error:
        logger.info("bcse-id callback error param", error=error)
        return fail("idp_error")
    if not code or not state:
        return fail("missing_params")

    parsed = sso.decode_state_cookie(lab_sso_state)
    if parsed is None:
        return fail("missing_state")
    expected_state, return_to = parsed
    if expected_state != state:
        return fail("state_mismatch")

    try:
        claims = await sso.exchange_code(code)
    except sso.SsoError as e:
        logger.warning("token exchange failed", error=str(e))
        return fail("exchange_failed")

    try:
        user = await sso.upsert_user_from_claims(db, claims)
    except sso.SsoError as e:
        logger.warning("user upsert failed", error=str(e))
        return fail("upsert_failed")

    access = issue_access_token(sub=str(user.id), role=user.role.value)
    refresh = issue_refresh_token(sub=str(user.id))

    redirect_target = return_to if return_to.startswith("/") else "/"
    resp = RedirectResponse(f"{frontend}{redirect_target}", status_code=302)
    set_auth_cookies(resp, access=access, refresh=refresh)
    resp.delete_cookie(STATE_COOKIE, path=STATE_COOKIE_PATH)

    await audit_log(
        db, actor=user, action="auth.sso.login",
        details={"role": user.role.value, "iss": claims.get("iss")},
        request=request,
    )
    await db.commit()
    return resp


# ── Webhook receiver ───────────────────────────────────────────────────

@webhook_router.post("/bcse-id")
async def bcse_id_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    body = await request.body()
    signature = request.headers.get("x-bcse-id-signature")
    if not sso.verify_webhook_signature(body, signature):
        logger.warning("bcse-id webhook signature mismatch")
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail={"code": "BAD_SIGNATURE"},
        )

    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail={"code": "INVALID_JSON"},
        )

    event_type = event.get("type")
    data = event.get("data") or {}
    identity_id = data.get("id") or data.get("identityId")
    if not identity_id:
        return {"status": "ignored", "reason": "no identity id"}

    user = (
        await db.execute(select(User).where(User.oidc_subject == identity_id))
    ).scalar_one_or_none()
    if user is None:
        # Identity not yet linked locally — nothing to update. Will be linked
        # lazily on next SSO login.
        return {"status": "ignored", "reason": "identity not linked"}

    if event_type == "identity.status_changed":
        new_status = data.get("status")
        # bcse-id status values mirror our is_active toggle
        if new_status == "disabled":
            user.is_active = False
        elif new_status in ("active", "enabled"):
            user.is_active = True
    elif event_type == "identity.updated":
        if (new_email := data.get("email")):
            user.email = new_email.lower().strip()
        if (new_name := data.get("name")):
            user.full_name = new_name
        if (new_code := data.get("vjuId") or data.get("studentCode")):
            user.student_code = new_code

    await audit_log(
        db, actor=None, action=f"webhook.bcse_id.{event_type}",
        target_type="user", target_id=str(user.id),
        details={"identityId": identity_id}, request=request,
    )
    await db.commit()
    return {"status": "applied"}
