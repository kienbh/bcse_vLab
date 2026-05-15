"""In-process SSE pub/sub. Single backend container → no Redis needed for pilot.

Two scopes for delivery:
- Per-user: target one specific user (e.g. notify requester of decision)
- Per-role broadcast: target everyone with a given role (e.g. notify all admins
  of a new reset request)

Subscribers register an asyncio.Queue via `subscribe(user)`. Publishers call
`publish(event, payload, ...)` which fans out non-blockingly. Slow consumers
that overflow their queue (>32 unread) get dropped.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.models import User, UserRole

logger = logging.getLogger(__name__)

_QUEUE_MAX = 32


@dataclass
class Subscriber:
    user_id: UUID
    role: UserRole
    queue: asyncio.Queue[tuple[str, dict[str, Any]]]


# Two-way index for fast fanout
_by_user: dict[UUID, set[Subscriber]] = defaultdict(set)
_by_role: dict[UserRole, set[Subscriber]] = defaultdict(set)


def subscribe(user: User) -> Subscriber:
    sub = Subscriber(
        user_id=user.id,
        role=user.role,
        queue=asyncio.Queue(maxsize=_QUEUE_MAX),
    )
    _by_user[user.id].add(sub)
    _by_role[user.role].add(sub)
    return sub


def unsubscribe(sub: Subscriber) -> None:
    _by_user[sub.user_id].discard(sub)
    _by_role[sub.role].discard(sub)


def _push(sub: Subscriber, event: str, payload: dict[str, Any]) -> None:
    try:
        sub.queue.put_nowait((event, payload))
    except asyncio.QueueFull:
        # Drop the subscriber; consumer is too slow. They'll reconnect.
        logger.warning(
            "event_bus: dropping slow subscriber user_id=%s role=%s", sub.user_id, sub.role
        )
        unsubscribe(sub)


def publish_to_user(user_id: UUID, event: str, payload: dict[str, Any]) -> int:
    """Send to every connection of a single user. Returns delivered count."""
    subs = list(_by_user.get(user_id, ()))
    for s in subs:
        _push(s, event, payload)
    return len(subs)


def publish_to_role(role: UserRole, event: str, payload: dict[str, Any]) -> int:
    """Send to every connection where the subscriber's role matches."""
    subs = list(_by_role.get(role, ()))
    for s in subs:
        _push(s, event, payload)
    return len(subs)


def publish_to_roles(roles: list[UserRole], event: str, payload: dict[str, Any]) -> int:
    total = 0
    for r in roles:
        total += publish_to_role(r, event, payload)
    return total
