"""Server-Sent Events stream — broadcasts device + session updates.

Per ADR-0009, SSE is the canonical real-time channel (not WebSocket).
For M0/M1 we provide a heartbeat + bridge to Redis pub/sub (filled in M3+).
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

router = APIRouter(prefix="/events", tags=["events"])


async def _heartbeat(request: Request, user: User) -> AsyncGenerator[str, None]:
    """Stream `: keepalive` every 15s + `event: hello` once at connect.

    Subsequent `event: device.status_changed` and `event: booking.update` will be
    dispatched here in M3+ via Redis pub/sub bridge.
    """
    yield f"event: hello\ndata: {json.dumps({'user_id': str(user.id), 'role': user.role.value})}\n\n"
    while True:
        if await request.is_disconnected():
            return
        ts = datetime.now(timezone.utc).isoformat()
        yield f": keepalive {ts}\n\n"
        try:
            await asyncio.sleep(15)
        except asyncio.CancelledError:
            return


@router.get("/stream")
async def stream(
    request: Request,
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    return StreamingResponse(
        _heartbeat(request, user),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # nginx hint
            "Connection": "keep-alive",
        },
    )
