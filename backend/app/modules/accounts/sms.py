"""OTP delivery. India requires DLT-registered sender IDs and templates.

The MSG91 request shape below follows their v5 "flow" API. Verify it against your provider account
before go-live; swap the class if you use a different provider.
"""

import logging
from typing import Protocol

import httpx

from app.core.config import get_settings

log = logging.getLogger(__name__)


class SmsSender(Protocol):
    async def send_otp(self, phone_e164: str, code: str) -> None: ...


class DevSmsSender:
    """OTP_DEV_MODE: sends nothing; the fixed dev OTP is accepted instead. The code is never logged."""

    async def send_otp(self, phone_e164: str, code: str) -> None:
        log.info("otp.dev_mode_skip_sms")


class Msg91SmsSender:
    URL = "https://control.msg91.com/api/v5/flow"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def send_otp(self, phone_e164: str, code: str) -> None:
        s = get_settings()
        resp = await self.client.post(
            self.URL,
            headers={"authkey": s.sms_api_key.get_secret_value(), "content-type": "application/json"},
            json={
                "template_id": s.sms_otp_template_id,
                "sender": s.sms_sender_id,
                "short_url": "0",
                "recipients": [{"mobiles": phone_e164.lstrip("+"), "otp": code}],
            },
            timeout=10.0,
        )
        if resp.status_code >= 400:
            # status only: the body may echo the phone number
            log.error("otp.sms_failed", extra={"status": resp.status_code})
            resp.raise_for_status()


_client: httpx.AsyncClient | None = None


def get_sms_sender() -> SmsSender:
    global _client
    if get_settings().otp_dev_mode:
        return DevSmsSender()
    if _client is None:
        _client = httpx.AsyncClient()
    return Msg91SmsSender(_client)
