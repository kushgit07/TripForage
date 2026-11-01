"""Resend email delivery, isolated behind a small interface.

Originally used SendGrid; swapped to Resend because SendGrid's free-tier
signup fraud checks were blocking new accounts outright. Resend has the same
shape (free tier, no card, transactional HTTP API) with a much smoother
signup flow. Kept as its own service (rather than inline in the agent) so it
can be unit-tested with a mocked client and swapped out later without
touching the agent graph.
"""

from __future__ import annotations

import logging

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

_RESEND_API_URL = "https://api.resend.com/emails"


class EmailDeliveryError(RuntimeError):
    """Raised when Resend rejects or fails to send the email."""


class EmailService:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
    )
    def send_html_email(self, *, from_email: str, to_email: str, subject: str, html_content: str) -> None:
        if not self._api_key:
            raise EmailDeliveryError("RESEND_API_KEY is not configured.")

        payload = {"from": from_email, "to": [to_email], "subject": subject, "html": html_content}
        response = requests.post(
            _RESEND_API_URL,
            json=payload,
            headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
            timeout=15,
        )

        if response.status_code >= 300:
            logger.warning("Resend API error %s: %s", response.status_code, response.text[:300])
            raise EmailDeliveryError(f"Resend returned status {response.status_code}: {response.text[:300]}")

        logger.info("Email sent to %s (status %s)", to_email, response.status_code)
