from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

_RETRYABLE_STATUSES: set[int] = {429, 500, 502, 503, 504}
_DEFAULT_TIMEOUT: float = 30.0
_DEFAULT_CONNECT_TIMEOUT: float = 10.0
_DEFAULT_MAX_RETRIES: int = 3
_DEFAULT_BACKOFF: float = 1.0

_logger = logging.getLogger("shuyuancore.models.http")


class HttpxClient:

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
        connect_timeout: float = _DEFAULT_CONNECT_TIMEOUT,
        max_retries: int = _DEFAULT_MAX_RETRIES,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._connect_timeout = connect_timeout
        self._max_retries = max_retries

    async def _request(
        self,
        method: str,
        path: str,
        json_data: dict[str, Any] | None = None,
    ) -> httpx.Response:
        url = f"{self._base_url}{path}"
        headers: dict[str, str] = {
            "Content-Type": "application/json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(
                        self._timeout,
                        connect=self._connect_timeout,
                    ),
                ) as client:
                    response = await client.request(
                        method, url, headers=headers, json=json_data
                    )

                if response.status_code == 429 and attempt < self._max_retries:
                    wait = _DEFAULT_BACKOFF * (2 ** (attempt - 1))
                    _logger.warning(
                        "rate_limited attempt=%d wait=%.1f status=%d",
                        attempt,
                        wait,
                        response.status_code,
                    )
                    await asyncio.sleep(wait)
                    continue

                if response.status_code in _RETRYABLE_STATUSES and attempt < self._max_retries:
                    wait = _DEFAULT_BACKOFF * (2 ** (attempt - 1))
                    _logger.warning(
                        "retryable_error attempt=%d wait=%.1f status=%d",
                        attempt,
                        wait,
                        response.status_code,
                    )
                    await asyncio.sleep(wait)
                    continue

                response.raise_for_status()
                return response

            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_error = exc
                if attempt < self._max_retries:
                    wait = _DEFAULT_BACKOFF * (2 ** (attempt - 1))
                    _logger.warning(
                        "request_timeout attempt=%d wait=%.1f error=%s",
                        attempt,
                        wait,
                        exc,
                    )
                    await asyncio.sleep(wait)
                else:
                    raise

            except httpx.HTTPStatusError as exc:
                last_error = exc
                if (
                    exc.response.status_code in _RETRYABLE_STATUSES
                    and attempt < self._max_retries
                ):
                    wait = _DEFAULT_BACKOFF * (2 ** (attempt - 1))
                    await asyncio.sleep(wait)
                else:
                    raise

        raise last_error or RuntimeError("unexpected_retry_exhaustion")

    async def post(
        self,
        path: str,
        json_data: dict[str, Any] | None = None,
    ) -> httpx.Response:
        return await self._request("POST", path, json_data)

    async def get(
        self,
        path: str,
    ) -> httpx.Response:
        return await self._request("GET", path)
