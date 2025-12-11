from __future__ import annotations
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta
from typing import Deque, Dict
from .config_loader import ROUTING_CFG

cfg = ROUTING_CFG.get("ids", {})
WINDOW_SECONDS = cfg.get("window_seconds", 5)
MAX_MSGS_PER_WINDOW = cfg.get("max_msgs_per_window", 20)
DUP_TTL_SECONDS = cfg.get("duplicate_suppression_ttl", 600)

_peer_windows: Dict[str, Deque[datetime]] = defaultdict(deque)
_seen_msg_ids: Dict[str, float] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def is_rate_limited(peer: str) -> bool:
    window = _peer_windows[peer]
    now = _now()
    cutoff = now - timedelta(seconds=WINDOW_SECONDS)

    while window and window[0] < cutoff:
        window.popleft()

    if len(window) >= MAX_MSGS_PER_WINDOW:
        return True

    window.append(now)
    return False


def is_duplicate(msg_id: str) -> bool:
    now = _now().timestamp()
    cutoff = now - DUP_TTL_SECONDS

    for mid, ts in list(_seen_msg_ids.items()):
        if ts < cutoff:
            del _seen_msg_ids[mid]

    if msg_id in _seen_msg_ids:
        return True

    _seen_msg_ids[msg_id] = now
    return False
