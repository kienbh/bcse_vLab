"""Server-Sent Events stream — broadcasts device + reset-request updates.

Per ADR-0009, SSE is the canonical real-time channel (not WebSocket).
Connects each authenticated client to the in-process event_bus and forwards
queued events as SSE messages. Sends a `: keepalive` comment every 15s to
prevent reverse-proxy idle timeouts.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user
from app.models import User
from app.services import event_bus

router = APIRouter(prefix="/events", tags=["events"])


async def _stream(request: Request, user: User) -> AsyncGenerator[str, None]:
    sub = event_bus.subscribe(user)
    yield f"event: hello\ndata: {json.dumps({'user_id': str(user.id), 'role': user.role.value})}\n\n"
    try:
        while True:
            if await request.is_disconnected():
                return
            try:
                event, payload = await asyncio.wait_for(sub.queue.get(), timeout=15.0)
                yield f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"
            except asyncio.TimeoutError:
                # Idle — send keepalive comment
                ts = datetime.now(timezone.utc).isoformat()
                yield f": keepalive {ts}\n\n"
            except asyncio.CancelledError:
                return
    finally:
        event_bus.unsubscribe(sub)


@router.get("/stream")
async def stream(
    request: Request,
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    return StreamingResponse(
        _stream(request, user),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # nginx hint
            "Connection": "keep-alive",
        },
    )
