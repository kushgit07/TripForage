"""Thin client for the Duffel API (flights + Duffel Stays for hotels).

Replaces `amadeus_client.py`. Amadeus shut down its Self-Service developer
portal on 2026-07-17; Duffel is the recommended migration path — free test
mode, no card required, and it covers both flights and hotels through one
provider instead of two.

Differences from the Amadeus client this replaces:
- Auth is a single static bearer token (a "duffel_test_..." or
  "duffel_live_..." API key created in the Duffel dashboard) — there's no
  OAuth2 client-credentials dance or token refresh to manage.
- Every request needs a `Duffel-Version` header pinning the API version,
  in addition to the bearer token.
- Same resilience shape as before: retries with exponential backoff on
  transient network errors only, a typed `DuffelAPIError` on 4xx/5xx so
  callers get a clean message instead of a raw `requests` exception.
"""

from __future__ import annotations

import logging

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class DuffelAPIError(RuntimeError):
    """Raised when the Duffel API returns an error or is unreachable after retries."""


class DuffelClient:
    def __init__(self, api_key: str, base_url: str = "https://api.duffel.com", api_version: str = "v2") -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Duffel-Version": api_version,
            "Accept": "application/json",
        }

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
    )
    def get(self, path: str, params: dict | None = None) -> dict:
        response = requests.get(
            f"{self._base_url}{path}",
            params={k: v for k, v in (params or {}).items() if v is not None},
            headers=self._headers,
            timeout=15,
        )
        return self._parse(response, path)

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
    )
    def post(self, path: str, json_body: dict, params: dict | None = None) -> dict:
        response = requests.post(
            f"{self._base_url}{path}",
            params={k: v for k, v in (params or {}).items() if v is not None},
            json=json_body,
            headers={**self._headers, "Content-Type": "application/json"},
            timeout=15,
        )
        return self._parse(response, path)

    @staticmethod
    def _parse(response: requests.Response, path: str) -> dict:
        if response.status_code >= 400:
            logger.warning("Duffel API error %s on %s: %s", response.status_code, path, response.text[:300])
            raise DuffelAPIError(f"Duffel request to {path} failed ({response.status_code}): {response.text[:300]}")
        return response.json()
