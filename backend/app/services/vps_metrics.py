"""VPS-GPU live metrics — SSH `nvidia-smi` + `df` with a Redis-cached snapshot.

M6.5. The student VPS list shows a per-card badge (GPU util, VRAM, disk free)
so SVs can pick a less-loaded GPU box BEFORE blocking, and a sidebar panel
inside the block detail showing the same plus the GPU process list.

Cache strategy
--------------
- Redis key `vps:metrics:{device_id}` with TTL 25 s.
- The frontend polls every 30 s, so a cache hit is almost guaranteed during
  a steady-state browsing session — first miss in a 30 s window pays one
  SSH round trip, the rest of that window is free.
- Per-device asyncio.Lock dedupes concurrent misses inside a single
  backend process (10 students opening the list together → 1 SSH per VPS,
  not 10).
- If Redis is down we degrade to "SSH every call" — log a warning, the
  feature still works. Redis was declared in compose since M0 but this is
  the first wire-up; we don't want a metrics view outage to drag the rest
  of the site down.

Mock mode
---------
`MOCK_SSH_DEVICES=true` (the same env var the SSH manager honours) returns
synthesised numbers so devs without a real GPU VPS can iterate on UI.
"""
from __future__ import annotations

import asyncio
import json
import os
import random
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncssh
from loguru import logger

from app.core.config import get_settings
from app.services.ssh_manager import is_mock_mode

# 25 s — see module docstring.
CACHE_TTL_SECONDS = 25
# Hard SSH timeout — a hung VPS shouldn't freeze the dashboard.
SSH_TIMEOUT_SECONDS = 6

_REDIS_KEY_PREFIX = "vps:metrics:"

# Per-device lock so concurrent cache-miss callers collapse to a single SSH.
# Module-level state is fine — uvicorn runs a single event loop per worker
# and we don't horizontally scale workers in the pilot.
_locks: dict[str, asyncio.Lock] = {}

# Lazy Redis client. None when Redis is unreachable — every call retries
# until the connection comes back; the in-memory dict below is the fallback
# so users still see fresh data.
_redis_client: Any | None = None
_redis_init_lock = asyncio.Lock()
# In-process fallback cache when Redis is unreachable. Same TTL contract.
_memory_cache: dict[str, tuple[float, str]] = {}


@dataclass
class GpuSnapshot:
    name: str
    util_pct: int
    vram_used_mb: int
    vram_total_mb: int
    temp_c: int


@dataclass
class DiskSnapshot:
    mount: str
    used_bytes: int
    total_bytes: int
    free_bytes: int


@dataclass
class GpuProcess:
    pid: int
    vram_mb: int
    name: str


@dataclass
class VpsMetrics:
    device_id: str
    fetched_at: str
    cached: bool = False
    error: str | None = None
    gpu: GpuSnapshot | None = None
    disk: DiskSnapshot | None = None
    processes: list[GpuProcess] = field(default_factory=list)
    # Actual bytes used inside the VPS's own data space ($HOME of the SSH
    # user) — measured with `du`, NOT `df`. On co-located VPS (ai01/02/03
    # share one ext4 host filesystem) `df` reports the whole 1.8 TB host;
    # `du $HOME` is the only ground-truth for "how much is this VPS using
    # of its 300 GB quota". None when the du probe failed/timed out.
    home_used_bytes: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Redis helpers
# ---------------------------------------------------------------------------

async def _get_redis():
    """Lazy-create the async Redis client. Returns None when unreachable."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    async with _redis_init_lock:
        if _redis_client is not None:
            return _redis_client
        try:
            # Import inside the function — `redis` is an optional infra
            # dependency for now; keeping the import lazy means the rest of
            # the backend boots even if the package is missing at install.
            from redis import asyncio as aioredis  # type: ignore
        except ImportError:
            logger.warning("redis package not installed — VPS metrics cache disabled")
            return None
        try:
            settings = get_settings()
            client = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_timeout=2,
                socket_connect_timeout=2,
            )
            await client.ping()
            _redis_client = client
            logger.info("vps_metrics: Redis cache attached at {}", settings.REDIS_HOST)
            return _redis_client
        except Exception as e:
            # Redis can fail in many ways (DNS, auth, network) — degrade
            # to in-memory cache rather than 500-ing the metrics endpoint.
            logger.warning("vps_metrics: Redis unreachable ({}), using in-memory cache", e)
            return None


async def _cache_get(device_id: str) -> dict[str, Any] | None:
    r = await _get_redis()
    if r is not None:
        try:
            raw = await r.get(_REDIS_KEY_PREFIX + device_id)
            if raw:
                return json.loads(raw)
        except Exception as e:
            logger.warning("vps_metrics: Redis GET failed ({}), falling back", e)
    # Fallback: in-memory
    entry = _memory_cache.get(device_id)
    if entry is None:
        return None
    expires_at, raw = entry
    loop = asyncio.get_event_loop()
    if loop.time() > expires_at:
        _memory_cache.pop(device_id, None)
        return None
    return json.loads(raw)


async def _cache_set(device_id: str, payload: dict[str, Any]) -> None:
    raw = json.dumps(payload)
    r = await _get_redis()
    if r is not None:
        try:
            await r.set(_REDIS_KEY_PREFIX + device_id, raw, ex=CACHE_TTL_SECONDS)
            return
        except Exception as e:
            logger.warning("vps_metrics: Redis SET failed ({}), using memory fallback", e)
    loop = asyncio.get_event_loop()
    _memory_cache[device_id] = (loop.time() + CACHE_TTL_SECONDS, raw)


# ---------------------------------------------------------------------------
# SSH probes
# ---------------------------------------------------------------------------


def _gpu_query(gpu_index: int | None) -> str:
    # `--id=N` scopes nvidia-smi to one physical GPU. Without it, a
    # multi-GPU host (ai01/ai02/ai03 share bcseserver1's 3x RTX 6000 Ada)
    # returns one CSV line per GPU and we'd silently read GPU 0 for every
    # slot — see the incident where ai02/ai03 both showed ai01's load.
    # CUDA_VISIBLE_DEVICES in the SSH user's .bashrc does NOT help here:
    # asyncssh's non-interactive `conn.run()` doesn't source login-shell
    # rc files, so the pin from /etc/profile.d/vlab-gpu-pin.sh never
    # applies. `--id` is passed explicitly instead, sourced from
    # device.capabilities.gpu_index (DB), independent of shell init.
    id_flag = f"--id={gpu_index} " if gpu_index is not None else ""
    return (
        f"nvidia-smi {id_flag}--query-gpu=name,utilization.gpu,memory.used,memory.total,"
        "temperature.gpu --format=csv,noheader,nounits"
    )


_DISK_QUERY = "df -B1 --output=avail,size,target /home | tail -n 1"
# Bytes used inside the SSH user's own home — the VPS's real footprint
# against its quota. `-x` stays on one filesystem (don't descend into
# bind-mounts); `$HOME` is correct because we SSH in AS the VPS user.
_HOME_DU_QUERY = 'du -sbx "$HOME" 2>/dev/null | cut -f1'
# du can be slow on a home with hundreds of GB — give it more headroom
# than the other near-instant queries. Cache TTL (25 s) absorbs the cost.
HOME_DU_TIMEOUT_SECONDS = 20


def _proc_query(gpu_index: int | None) -> str:
    # Same scoping issue as _gpu_query — without --id this lists compute
    # processes across every GPU on the host, so a co-located slot would
    # see (and misattribute) another slot's process list.
    id_flag = f"--id={gpu_index} " if gpu_index is not None else ""
    return (
        f"nvidia-smi {id_flag}--query-compute-apps=pid,used_memory,process_name "
        "--format=csv,noheader,nounits"
    )


def _parse_gpu(stdout: str) -> GpuSnapshot | None:
    line = stdout.strip().splitlines()[0] if stdout.strip() else ""
    if not line:
        return None
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 5:
        return None
    try:
        return GpuSnapshot(
            name=parts[0],
            util_pct=int(parts[1]),
            vram_used_mb=int(parts[2]),
            vram_total_mb=int(parts[3]),
            temp_c=int(parts[4]),
        )
    except ValueError:
        return None


def _parse_disk(stdout: str) -> DiskSnapshot | None:
    line = stdout.strip()
    if not line:
        return None
    # `df -B1 --output=avail,size,target` prints "<avail> <size> <mount>".
    # The header is stripped by `tail -n 1`; whitespace separates fields.
    parts = line.split()
    if len(parts) < 3:
        return None
    try:
        avail = int(parts[0])
        size = int(parts[1])
        mount = parts[2]
        return DiskSnapshot(
            mount=mount,
            free_bytes=avail,
            total_bytes=size,
            used_bytes=size - avail,
        )
    except ValueError:
        return None


def _parse_home_used(stdout: str) -> int | None:
    line = stdout.strip().splitlines()[0] if stdout.strip() else ""
    if not line or not line.isdigit():
        return None
    return int(line)


def _parse_processes(stdout: str) -> list[GpuProcess]:
    out: list[GpuProcess] = []
    for raw in stdout.strip().splitlines():
        parts = [p.strip() for p in raw.split(",")]
        if len(parts) < 3:
            continue
        try:
            out.append(
                GpuProcess(
                    pid=int(parts[0]),
                    vram_mb=int(parts[1]) if parts[1].isdigit() else 0,
                    name=parts[2],
                )
            )
        except ValueError:
            continue
    return out


def _mock_snapshot(device_id: str) -> VpsMetrics:
    rng = random.Random(device_id + str(int(datetime.now().timestamp() // CACHE_TTL_SECONDS)))
    util = rng.randint(2, 85)
    vram_total = 49152
    vram_used = int(vram_total * (util / 100) * rng.uniform(0.4, 0.9))
    return VpsMetrics(
        device_id=device_id,
        fetched_at=datetime.now(UTC).isoformat(),
        gpu=GpuSnapshot(
            name="NVIDIA RTX 6000 Ada (mock)",
            util_pct=util,
            vram_used_mb=vram_used,
            vram_total_mb=vram_total,
            temp_c=rng.randint(38, 74),
        ),
        disk=DiskSnapshot(
            mount="/home",
            total_bytes=500 * 1024**3,
            free_bytes=int((500 - rng.randint(50, 400)) * 1024**3),
            used_bytes=0,
        ),
        home_used_bytes=rng.randint(5, 280) * 1024**3,
        processes=[
            GpuProcess(pid=1000 + i, vram_mb=rng.randint(512, 8192), name=name)
            for i, name in enumerate(rng.sample(
                ["python3", "jupyter", "ollama", "torchrun", "vllm"], k=rng.randint(0, 3)
            ))
        ],
    )


async def _ssh_probe(
    *,
    device_id: str,
    internal_ip: str,
    ssh_port: int,
    ssh_user: str,
    gpu_index: int | None,
) -> VpsMetrics:
    """One SSH session, three commands, parsed into a snapshot.

    On any SSH-level failure we return a snapshot with `error` set rather
    than raising — the UI can render "—" cells and a small error chip
    instead of going blank.
    """
    settings = get_settings()
    key_path = settings.BACKEND_SSH_KEY_PATH
    fetched_at = datetime.now(UTC).isoformat()
    if not os.path.exists(key_path):
        return VpsMetrics(
            device_id=device_id,
            fetched_at=fetched_at,
            error="SSH_KEY_MISSING",
        )
    try:
        async with asyncssh.connect(
            internal_ip,
            port=ssh_port,
            username=ssh_user,
            client_keys=[key_path],
            known_hosts=None,
            connect_timeout=SSH_TIMEOUT_SECONDS,
        ) as conn:
            # Run the three queries concurrently on one connection. asyncssh
            # multiplexes them over the same TCP socket → ~1 RTT.
            gpu_r, disk_r, proc_r, home_r = await asyncio.gather(
                conn.run(_gpu_query(gpu_index), check=False, timeout=SSH_TIMEOUT_SECONDS),
                conn.run(_DISK_QUERY, check=False, timeout=SSH_TIMEOUT_SECONDS),
                conn.run(_proc_query(gpu_index), check=False, timeout=SSH_TIMEOUT_SECONDS),
                conn.run(_HOME_DU_QUERY, check=False, timeout=HOME_DU_TIMEOUT_SECONDS),
                return_exceptions=True,
            )
    except (asyncssh.Error, OSError, TimeoutError) as e:
        return VpsMetrics(
            device_id=device_id,
            fetched_at=fetched_at,
            error=f"SSH_FAIL: {type(e).__name__}",
        )

    def _stdout(r: Any) -> str:
        if isinstance(r, Exception):
            return ""
        return getattr(r, "stdout", "") or ""

    return VpsMetrics(
        device_id=device_id,
        fetched_at=fetched_at,
        gpu=_parse_gpu(_stdout(gpu_r)),
        disk=_parse_disk(_stdout(disk_r)),
        processes=_parse_processes(_stdout(proc_r)),
        home_used_bytes=_parse_home_used(_stdout(home_r)),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def get_metrics(
    *,
    device_id: UUID | str,
    internal_ip: str,
    ssh_port: int,
    ssh_user: str,
    gpu_index: int | None = None,
) -> VpsMetrics:
    """Return a cached snapshot, fetching via SSH on cache miss.

    Concurrent miss callers for the same device collapse to a single SSH
    via per-device asyncio.Lock.
    """
    did = str(device_id)
    cached = await _cache_get(did)
    if cached is not None:
        cached["cached"] = True
        return _hydrate(cached)

    lock = _locks.setdefault(did, asyncio.Lock())
    async with lock:
        # Double-check inside the lock — another coroutine may have just
        # populated the cache while we were waiting.
        cached = await _cache_get(did)
        if cached is not None:
            cached["cached"] = True
            return _hydrate(cached)

        if is_mock_mode():
            snap = _mock_snapshot(did)
        else:
            snap = await _ssh_probe(
                device_id=did,
                internal_ip=internal_ip,
                ssh_port=ssh_port,
                ssh_user=ssh_user,
                gpu_index=gpu_index,
            )
        await _cache_set(did, snap.to_dict())
        return snap


def _hydrate(raw: dict[str, Any]) -> VpsMetrics:
    """Rebuild a VpsMetrics from a cached JSON dict."""
    gpu = raw.get("gpu")
    disk = raw.get("disk")
    procs = raw.get("processes") or []
    return VpsMetrics(
        device_id=raw["device_id"],
        fetched_at=raw["fetched_at"],
        cached=bool(raw.get("cached", False)),
        error=raw.get("error"),
        gpu=GpuSnapshot(**gpu) if gpu else None,
        disk=DiskSnapshot(**disk) if disk else None,
        processes=[GpuProcess(**p) for p in procs],
        home_used_bytes=raw.get("home_used_bytes"),
    )
