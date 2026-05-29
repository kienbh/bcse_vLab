"""Email notifier — best-effort SMTP send for proposal notifications.

Synchronous smtplib wrapped in asyncio.to_thread; if SMTP isn't configured
or the send fails we log a warning and return False so the caller can still
finish the request flow (in-portal access_request row stays — the email is
a nice-to-have, not the source of truth).
"""
from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage

from loguru import logger

from app.core.config import get_settings


def _send_sync(*, to_addrs: list[str], subject: str, body: str) -> bool:
    settings = get_settings()
    pw = settings.SMTP_PASSWORD.get_secret_value().strip()
    if not pw:
        logger.warning("SMTP not configured (SMTP_PASSWORD empty) — skipping email")
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM}>"
    msg["To"] = ", ".join(to_addrs)
    msg.set_content(body)
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as s:
            s.starttls()
            s.login(settings.SMTP_USER, pw)
            s.send_message(msg)
        logger.info("proposal email sent to={}", to_addrs)
        return True
    except Exception as e:
        logger.error("SMTP send failed: {}", e)
        return False


async def send_proposal_email(
    *,
    student_email: str,
    student_name: str,
    student_code: str | None,
    device_name: str,
    requested_from: str,
    requested_to: str,
    reason: str,
    request_id: str,
) -> bool:
    """Notify the lecturer about a new VPS access proposal.

    Recipient is `Settings.LECTURER_NOTIFICATION_EMAIL` (single address; comma-
    separate for multiple lecturers). Returns True if the SMTP send succeeded.
    """
    settings = get_settings()
    to_field = (settings.LECTURER_NOTIFICATION_EMAIL or "").strip()
    if not to_field:
        logger.warning("LECTURER_NOTIFICATION_EMAIL empty — skipping proposal email")
        return False
    to_addrs = [a.strip() for a in to_field.split(",") if a.strip()]
    subject = (
        f"[VJU Lab Portal] Yêu cầu VPS dài hạn — "
        f"{student_name} ({student_code or student_email})"
    )
    body = (
        f"Sinh viên: {student_name}\n"
        f"Email     : {student_email}\n"
        f"MSV       : {student_code or '(không có)'}\n"
        f"\n"
        f"VPS yêu cầu: {device_name}\n"
        f"Khoảng thời gian: {requested_from} → {requested_to}\n"
        f"\n"
        f"Mục đích sử dụng:\n"
        f"{reason}\n"
        f"\n"
        f"---\n"
        f"Duyệt yêu cầu tại: https://sv14.bcse-vju.com/admin/vps-access\n"
        f"Request ID: {request_id}\n"
    )
    return await asyncio.to_thread(_send_sync, to_addrs=to_addrs, subject=subject, body=body)
