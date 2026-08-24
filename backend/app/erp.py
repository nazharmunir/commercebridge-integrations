import os
import time
from dataclasses import dataclass
from typing import Callable
from uuid import uuid4

import httpx

from .models import CanonicalOrder


class ERPDeliveryError(RuntimeError):
    def __init__(self, message: str, attempts: int):
        super().__init__(message)
        self.attempts = attempts


@dataclass
class ERPDeliveryResult:
    reference: str
    attempts: int
    processing_ms: int


class ERPClient:
    """ERP gateway with retry/backoff and a safe simulator fallback for the portfolio demo."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        max_attempts: int = 3,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = base_url or os.getenv("ERP_BASE_URL")
        self.api_key = api_key or os.getenv("ERP_API_KEY")
        self.max_attempts = max_attempts
        self.sleep_fn = sleep_fn

    def deliver(self, order: CanonicalOrder, simulate_timeout: bool = False) -> ERPDeliveryResult:
        started = time.perf_counter()
        last_error = "ERP delivery failed"

        for attempt in range(1, self.max_attempts + 1):
            try:
                if simulate_timeout:
                    raise httpx.TimeoutException("simulated ERP timeout")

                if not self.base_url:
                    elapsed = int((time.perf_counter() - started) * 1000)
                    return ERPDeliveryResult(
                        reference=f"ERP-{uuid4().hex[:10].upper()}",
                        attempts=attempt,
                        processing_ms=max(elapsed, 1),
                    )

                headers = {"Content-Type": "application/json"}
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"

                response = httpx.post(
                    f"{self.base_url.rstrip('/')}/orders",
                    json=order.model_dump(mode="json"),
                    headers=headers,
                    timeout=5.0,
                )
                response.raise_for_status()
                payload = response.json() if response.content else {}
                elapsed = int((time.perf_counter() - started) * 1000)
                return ERPDeliveryResult(
                    reference=str(payload.get("reference") or response.headers.get("x-request-id") or f"ERP-{uuid4().hex[:10].upper()}"),
                    attempts=attempt,
                    processing_ms=max(elapsed, 1),
                )
            except (httpx.TimeoutException, httpx.HTTPError) as exc:
                last_error = str(exc) or exc.__class__.__name__
                if attempt < self.max_attempts:
                    self.sleep_fn(0.25 * (2 ** (attempt - 1)))

        raise ERPDeliveryError(f"ERP gateway failed after {self.max_attempts} delivery attempts: {last_error}", self.max_attempts)
