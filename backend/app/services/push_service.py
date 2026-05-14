"""Push notification dispatch.

Sends to FCM HTTP v1 and APNs HTTP/2. Both providers' SDKs require real
credentials, so this module exposes the right shape and falls back to a
log-only dry-run when credentials are missing — keeps local dev painless
while the production wiring is one config change away.
"""

import logging
import os
from typing import Iterable

import httpx
from sqlalchemy.orm import Session

from app.models import Device

log = logging.getLogger(__name__)

FCM_ENDPOINT = "https://fcm.googleapis.com/v1/projects/{project}/messages:send"
APNS_ENDPOINT = "https://api.push.apple.com/3/device/{token}"


async def deliver(
    db: Session,
    user_ids: Iterable[int],
    title: str,
    body: str,
    data: dict | None = None,
) -> int:
    devices = list(db.query(Device).filter(Device.user_id.in_(list(user_ids))).all())
    if not devices:
        return 0

    sent = 0
    async with httpx.AsyncClient(timeout=5.0) as client:
        for d in devices:
            try:
                if d.platform == "fcm":
                    await _send_fcm(client, d.token, title, body, data or {})
                elif d.platform == "apns":
                    await _send_apns(client, d.token, title, body, data or {})
                else:
                    log.info(
                        "dry-run push platform=%s token=%s title=%s",
                        d.platform,
                        d.token[:12],
                        title,
                    )
                sent += 1
            except Exception as e:
                # One bad token must not stop the rest of the batch.
                log.warning("push failed device=%s err=%s", d.id, e)
    return sent


async def _send_fcm(
    client: httpx.AsyncClient, token: str, title: str, body: str, data: dict
) -> None:
    project = os.getenv("FCM_PROJECT_ID")
    bearer = os.getenv(
        "FCM_ACCESS_TOKEN"
    )  # service-account access token refreshed elsewhere
    if not (project and bearer):
        log.info("dry-run FCM token=%s title=%s", token[:12], title)
        return
    r = await client.post(
        FCM_ENDPOINT.format(project=project),
        headers={
            "Authorization": f"Bearer {bearer}",
            "Content-Type": "application/json",
        },
        json={
            "message": {
                "token": token,
                "notification": {"title": title, "body": body},
                "data": data,
            }
        },
    )
    r.raise_for_status()


async def _send_apns(
    client: httpx.AsyncClient, token: str, title: str, body: str, data: dict
) -> None:
    bearer = os.getenv("APNS_JWT")
    bundle = os.getenv("APNS_BUNDLE_ID")
    if not (bearer and bundle):
        log.info("dry-run APNs token=%s title=%s", token[:12], title)
        return
    r = await client.post(
        APNS_ENDPOINT.format(token=token),
        headers={
            "authorization": f"bearer {bearer}",
            "apns-topic": bundle,
            "apns-push-type": "alert",
        },
        json={"aps": {"alert": {"title": title, "body": body}}, **data},
    )
    r.raise_for_status()
