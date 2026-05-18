"""Single-shot delivery with exponential backoff retry."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal

import httpx

DeliveryStatusValue = Literal["delivered", "failed"]


@dataclass(frozen=True)
class DeliveryResult:
    status: DeliveryStatusValue
    attempts: int


async def deliver(
    *,
    payload: dict,
    endpoint: str,
    max_attempts: int = 3,
    backoff_seconds: tuple[float, ...] = (1.0, 2.0, 4.0),
    timeout_seconds: float = 5.0,
) -> DeliveryResult:
    """POST `payload` to `endpoint` with exp-backoff retry on 5xx / network errors.

    - 2xx response -> delivered.
    - 4xx response -> failed immediately (no retry; bad request won't get better).
    - 5xx or transport error -> retry up to `max_attempts` total tries,
      sleeping `backoff_seconds[attempt-1]` between tries.
    """
    last_attempt = 0
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        for attempt in range(1, max_attempts + 1):
            last_attempt = attempt
            try:
                resp = await client.post(endpoint, json=payload)
            except httpx.HTTPError:
                if attempt < max_attempts:
                    await asyncio.sleep(backoff_seconds[attempt - 1])
                continue

            if 200 <= resp.status_code < 300:
                return DeliveryResult(status="delivered", attempts=attempt)
            if 400 <= resp.status_code < 500:
                return DeliveryResult(status="failed", attempts=attempt)
            # 5xx -> retry
            if attempt < max_attempts:
                await asyncio.sleep(backoff_seconds[attempt - 1])

    return DeliveryResult(status="failed", attempts=last_attempt)
