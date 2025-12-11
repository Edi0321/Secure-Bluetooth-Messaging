# routing_api.py
# uvicorn routing_api:app --host 0.0.0.0 --port 8000 --reload
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, Request, Depends

from .config_loader import ROUTING_CFG
from .envelope import MessageEnvelope
from .errors import http_error, ErrorCode
from .auth import DEVICE_FP_HEADER, DEVICE_TOKEN_HEADER, verify_api_token
from .utils import hash_token

from .routing_db import init_db, enqueue_message, get_outgoing, mark_delivered
from .routing_loop import routing_loop
from .ids_module import is_rate_limited, is_duplicate

MAX_ENVELOPE_BYTES = ROUTING_CFG.get("max_envelope_bytes", 16_384)
MAX_TTL = ROUTING_CFG.get("max_ttl", 8)
DEFAULT_TTL = ROUTING_CFG.get("ttl_default", 4)

router = APIRouter()

DEV_DEVICE_FP = "DEV-ROUTER-CLIENT"
DEV_DEVICE_TOKEN = "dev-router-token"
DEV_DEVICE_TOKEN_HASH = hash_token(DEV_DEVICE_TOKEN)

DEV_DEVICES = {
    DEV_DEVICE_FP: {
        "token_hash": DEV_DEVICE_TOKEN_HASH,
        "roles": {"gateway", "ble", "admin"},
    }
}


# helpers
def _base_auth(request: Request) -> str:
    client_ip = request.client.host or "unknown"
    bucket = f"auth:{client_ip}"

    device_fp = request.headers.get(DEVICE_FP_HEADER)
    token = request.headers.get(DEVICE_TOKEN_HEADER)

    if not device_fp or not token:
        if is_rate_limited(bucket):
            raise http_error(
                status_code=429,
                code=ErrorCode.UNAUTHORIZED,
                detail="Too many auth attempts for this device",
                retryable=True,
            )
        raise http_error(
            status_code=401,
            code=ErrorCode.UNAUTHORIZED,
            detail="Missing device auth headers",
            retryable=False,
        )

    dev_info = DEV_DEVICES.get(device_fp)
    if not dev_info or not verify_api_token(token, dev_info["token_hash"]):
        if is_rate_limited(bucket):
            raise http_error(
                status_code=429,
                code=ErrorCode.UNAUTHORIZED,
                detail="Too many auth attempts for this device",
                retryable=True,
            )
        raise http_error(
            status_code=401,
            code=ErrorCode.UNAUTHORIZED,
            detail="Invalid device credentials",
            retryable=False,
        )

    return device_fp


def require_device_auth(request: Request) -> str:
    return _base_auth(request)


def require_device_auth_role(role: str):
    async def _dep(request: Request) -> str:
        device_fp = _base_auth(request)
        dev_info = DEV_DEVICES.get(device_fp) or {}
        roles = dev_info.get("roles", set())
        if role not in roles:
            raise http_error(
                status_code=403,
                code=ErrorCode.FORBIDDEN,
                detail=f"Device missing required role: {role}",
                retryable=False,
            )
        return device_fp

    return _dep


# Startup helper
async def start_routing_loop() -> None:
    """Init DB and start background routing loop."""
    init_db()
    asyncio.create_task(routing_loop(interval_seconds=2.0))


# API endpoints
@router.post("/v1/router/enqueue")
def api_enqueue(
    envelope: MessageEnvelope,
    device_fp: str = Depends(require_device_auth),
):
    msg_id = envelope.header.msg_id
    ttl = envelope.header.ttl

    if ttl is None:
        ttl = DEFAULT_TTL
        envelope.header.ttl = ttl

    if ttl < 1 or ttl > MAX_TTL:
        raise http_error(
            400,
            ErrorCode.INVALID_INPUT,
            f"ttl must be between 1 and {MAX_TTL}",
            retryable=False,
        )

    if is_duplicate(msg_id):
        return {"queued": False, "msg_id": msg_id, "reason": "duplicate"}

    envelope_json = _check_envelope_size(
        envelope=envelope,
        peer=envelope.header.sender_fp,
        msg_id=msg_id,
    )

    try:
        enqueue_message(
            msg_id=msg_id,
            envelope_json=envelope_json,
            ttl=ttl,
            sender_fp=envelope.header.sender_fp,
            recipient_fp=envelope.header.recipient_fp,
        )
    except Exception as e:
        raise http_error(
            status_code=500,
            code=ErrorCode.DB_ERROR,
            detail=f"Failed to enqueue: {e}",
            retryable=False,
        )
    return {"queued": True, "msg_id": msg_id}


@router.get("/v1/router/outgoing_chunks")
def api_outgoing(
    limit: Optional[int] = 50,
    device_fp: str = Depends(require_device_auth_role("ble")),
):
    rows = get_outgoing()[: limit or 50]
    items = []
    for row in rows:
        items.append(
            {
                "chunk": row["envelope_json"],
                "target_peer": row["msg_id"],
            }
        )
    return {"items": items}


@router.post("/v1/router/mark_delivered")
def api_mark(
    payload: dict,
    device_fp: str = Depends(require_device_auth_role("ble")),
):
    row_id = payload.get("row_id")
    if row_id is None:
        raise http_error(
            status_code=400,
            code=ErrorCode.INVALID_INPUT,
            detail="row_id required",
            retryable=False,
        )
    mark_delivered(row_id)
    return {"ok": True}


@router.post("/v1/router/on_chunk_received")
def api_on_chunk_received(
    payload: dict,
    device_fp: str = Depends(require_device_auth_role("ble")),
):
    try:
        env = MessageEnvelope.model_validate(payload["chunk"])
    except Exception:
        raise http_error(
            status_code=400,
            code=ErrorCode.INVALID_INPUT,
            detail="invalid envelope from BLE",
            retryable=False,
        )

    msg_id = env.header.msg_id
    peer = env.header.sender_fp

    _check_envelope_size(
        envelope=env,
        peer=peer,
        msg_id=msg_id,
    )

    ttl = env.header.ttl
    if ttl is None or ttl <= 0:
        raise http_error(
            status_code=410,
            code=ErrorCode.TTL_EXPIRED,
            detail="ttl <= 0",
            retryable=False,
        )
    if ttl > MAX_TTL:
        raise http_error(
            status_code=400,
            code=ErrorCode.INVALID_INPUT,
            detail=f"ttl must be between 1 and {MAX_TTL}",
            retryable=False,
        )

    if is_duplicate(msg_id):
        return {"accepted": False, "action": "drop"}

    if ROUTING_CFG.get("forwarding_enabled", False):
        return {"accepted": True, "action": "forward"}
    else:
        return {"accepted": True, "action": "final"}


def _check_envelope_size(envelope: MessageEnvelope, peer: str, msg_id: str) -> str:
    env_json = envelope.model_dump_json()
    env_size = len(env_json.encode("utf-8"))
    if env_size > MAX_ENVELOPE_BYTES:
        raise http_error(
            status_code=413,
            code=ErrorCode.INVALID_INPUT,
            detail="envelope too large",
            retryable=False,
        )
    return env_json
