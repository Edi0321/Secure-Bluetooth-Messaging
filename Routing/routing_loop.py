# router_loop.py
from __future__ import annotations
import random
import asyncio
import json
from datetime import datetime, timezone
from math import pow

import httpx

from .config_loader import ROUTING_CFG
from .envelope import MessageEnvelope
from .utils import validate_ttl
from .auth import DEVICE_FP_HEADER, DEVICE_TOKEN_HEADER

from .routing_db import get_outgoing, mark_delivered, mark_dropped, increment_retry

BLE_ADAPTER_URL = ROUTING_CFG.get(
    "ble_adapter_url", "http://localhost:8000/v1/ble/send_chunk"
)

MAX_RETRIES = ROUTING_CFG.get("max_retries", 5)
BASE_BACKOFF_MS = ROUTING_CFG.get("base_retry_backoff_ms", 500)
BLE_DEVICE_FP = ROUTING_CFG.get("ble_device_fp", "DEV-BLE-ADAPTER")
BLE_DEVICE_TOKEN = ROUTING_CFG.get("ble_device_token", "dev-ble-token")

BLE_AUTH_HEADERS = {
    DEVICE_FP_HEADER: BLE_DEVICE_FP,
    DEVICE_TOKEN_HEADER: BLE_DEVICE_TOKEN,
}


def _parse_timestamp(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def _should_retry(row: dict) -> bool:
    retries = row["retries"]
    last_update = _parse_timestamp(row["last_update"])

    if retries == 0:
        return True

    backoff_ms = BASE_BACKOFF_MS * pow(2, retries - 1)

    jitter = ROUTING_CFG.get("retry_jitter_ms", 0)
    if jitter > 0:
        backoff_ms += random.randint(0, jitter)

    elapsed_ms = (
        datetime.now(timezone.utc) - last_update.replace(tzinfo=timezone.utc)
    ).total_seconds() * 1000.0

    return elapsed_ms >= backoff_ms


async def process_outgoing_queue() -> None:
    rows = get_outgoing()
    if not rows:
        return

    async with httpx.AsyncClient() as client:
        for row in rows:
            if not _should_retry(row):
                continue

            row_id = row["row_id"]
            env_json = row["envelope_json"]

            try:
                envelope = MessageEnvelope.parse_raw(env_json)
            except Exception as e:
                print(f"[Routing] invalid envelope JSON for row {row_id}: {e}")
                mark_dropped(row_id, reason="invalid_envelope")
                continue

            ttl = envelope.header.ttl

            if ttl is None or ttl <= 0:
                print(f"[Routing] dropping msg {envelope.header.msg_id}: TTL <= 0")
                mark_dropped(row_id, reason="ttl_expired")
                continue

            try:
                validate_ttl(ttl)
            except ValueError as exc:
                print(
                    f"[Routing] dropping msg {envelope.header.msg_id}: invalid TTL ({exc})"
                )
                mark_dropped(row_id, reason="ttl_invalid")
                continue

            if row["retries"] >= MAX_RETRIES:
                print(
                    f"[Routing] dropping msg {envelope.header.msg_id}: max_retries exceeded"
                )
                mark_dropped(row_id, reason="max_retries")
                continue

            envelope.header.ttl -= 1
            envelope.header.hop_count += 1

            try:
                resp = await client.post(
                    BLE_ADAPTER_URL,
                    json={"chunk": json.loads(envelope.json())},
                    headers=BLE_AUTH_HEADERS,
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    print(f"[Routing] delivered msg {envelope.header.msg_id}")
                    mark_delivered(row_id)
                else:
                    print(
                        f"[Routing] BLE error {resp.status_code} "
                        f"for {envelope.header.msg_id}: {resp.text}"
                    )
                    increment_retry(row_id)

            except Exception as e:
                print(f"[Routing] exception sending msg {envelope.header.msg_id}: {e}")
                increment_retry(row_id)


async def routing_loop(interval_seconds: float = 2.0):
    while True:
        await process_outgoing_queue()
        await asyncio.sleep(interval_seconds)
