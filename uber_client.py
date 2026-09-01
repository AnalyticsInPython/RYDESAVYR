"""OAuth login with Uber + a live UberX price/time estimate.

Setup (see README for the full walkthrough):
1. Create a developer app at https://developer.uber.com (self-serve with
   your own Uber account — no business approval needed until you want to
   go beyond yourself + 4 other registered developers).
2. Add http://127.0.0.1:5000/uber/callback as an authorized redirect URI.
3. Put UBER_CLIENT_ID / UBER_CLIENT_SECRET in a local .env file.

If those env vars aren't set, the app quietly skips this whole module and
falls back to the formula estimate in modes.py — nothing else breaks.

Caveat: developer.uber.com's docs are JavaScript-rendered, so the exact
response field names below (`price.low_estimate`, `trip.duration_estimate`,
etc.) are reconstructed from Uber's official Python SDK and cached doc
fragments rather than a fully confirmed live response. Test against a real
account and adjust `get_live_estimate` if a field is missing or renamed.
"""

import os
import time
from urllib.parse import urlencode

import requests

AUTH_BASE = "https://auth.uber.com/oauth/v2"
API_BASE = "https://api.uber.com/v1.2"
SCOPE = "request"
TARGET_PRODUCT = "UberX"

CLIENT_ID = os.environ.get("UBER_CLIENT_ID")
CLIENT_SECRET = os.environ.get("UBER_CLIENT_SECRET")


def is_configured() -> bool:
    return bool(CLIENT_ID and CLIENT_SECRET)


def authorize_url(redirect_uri: str, state: str) -> str:
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": SCOPE,
        "state": state,
    }
    return f"{AUTH_BASE}/authorize?{urlencode(params)}"


def exchange_code(code: str, redirect_uri: str) -> dict:
    response = requests.post(
        f"{AUTH_BASE}/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "code": code,
        },
        timeout=10,
    )
    response.raise_for_status()
    return _with_expiry(response.json())


def refresh_access_token(refresh_token: str) -> dict:
    response = requests.post(
        f"{AUTH_BASE}/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=10,
    )
    response.raise_for_status()
    return _with_expiry(response.json())


def _with_expiry(token_payload: dict) -> dict:
    token_payload["expires_at"] = time.time() + token_payload.get("expires_in", 0)
    return token_payload


def get_live_estimate(access_token: str, origin, destination):
    """Return {"price", "time" (minutes), "distance" (miles), "notes"} for
    UberX, or None if the account has no UberX nearby or anything about the
    live call fails — callers should fall back to the formula estimate.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        products_resp = requests.get(
            f"{API_BASE}/products",
            params={"latitude": origin[0], "longitude": origin[1]},
            headers=headers,
            timeout=10,
        )
        products_resp.raise_for_status()
        product = next(
            (p for p in products_resp.json().get("products", [])
             if p.get("display_name") == TARGET_PRODUCT),
            None,
        )
        if product is None:
            return None

        estimate_resp = requests.post(
            f"{API_BASE}/requests/estimate",
            json={
                "product_id": product["product_id"],
                "start_latitude": origin[0],
                "start_longitude": origin[1],
                "end_latitude": destination[0],
                "end_longitude": destination[1],
            },
            headers=headers,
            timeout=10,
        )
        estimate_resp.raise_for_status()
        data = estimate_resp.json()

        price = data.get("price") or {}
        trip = data.get("trip") or {}
        low, high = price.get("low_estimate"), price.get("high_estimate")
        if low is None or high is None:
            return None

        pickup_minutes = data.get("pickup_estimate") or 0
        duration_seconds = trip.get("duration_estimate") or 0
        distance_miles = trip.get("distance_estimate")

        return {
            "price": round((low + high) / 2, 2),
            "time": round(pickup_minutes + duration_seconds / 60, 1),
            "distance": round(distance_miles, 2) if distance_miles else None,
            "notes": "Live Uber quote.",
        }
    except (requests.RequestException, KeyError, TypeError, ValueError):
        return None
