"""The ONLY way the back-office changes anything: calls to PayForge's admin API."""

import httpx
from django.conf import settings


class ApiError(Exception):
    pass


def _call(method: str, path: str, json: dict | None = None) -> dict:
    try:
        response = httpx.request(
            method,
            f"{settings.PAYFORGE_API_URL}{path}",
            json=json,
            headers={"X-Admin-Token": settings.PAYFORGE_ADMIN_TOKEN},
            timeout=5.0,
        )
    except httpx.HTTPError as exc:
        raise ApiError(f"API unreachable: {exc}") from exc
    if response.status_code >= 400:
        try:
            message = response.json()["error"]["message"]
        except (ValueError, KeyError):
            message = response.text[:200]
        raise ApiError(f"HTTP {response.status_code}: {message}")
    return response.json()


def replay_delivery(delivery_id: str) -> dict:
    return _call("POST", f"/admin/webhook-deliveries/{delivery_id}/replay")


def set_merchant_status(merchant_id: str, status: str) -> dict:
    return _call("PATCH", f"/admin/merchants/{merchant_id}", {"status": status})
