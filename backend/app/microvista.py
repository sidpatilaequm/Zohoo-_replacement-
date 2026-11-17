import base64
import json
import logging
import os
import time
from typing import Any, Dict, Optional
import httpx
from fastapi import HTTPException

try:
    import certifi
    SSL_VERIFY: Any = certifi.where()
except Exception:
    SSL_VERIFY = True

logger = logging.getLogger("microvista")

_cached_token: Optional[str] = None
_token_expiry: float = 0.0

AUTH_URL = "https://kycapi.microvistatech.com/api/Auth/GenerateAuthtoken"
GSTIN_VERIFY_URL = "https://kycapi.microvistatech.com/api/v1/GstinVerification/GetGstinVerification"


def _extract_jwt_exp(token: str) -> float:
    try:
        parts = token.split(".")
        if len(parts) >= 2:
            payload = parts[1]
            padded = payload + "=" * ((4 - len(payload) % 4) % 4)
            data = json.loads(base64.urlsafe_b64decode(padded))
            exp = data.get("exp")
            if exp:
                return float(exp)
    except Exception as e:
        logger.warning("Could not extract exp from Microvista JWT: %s", e)
    return time.time() + 3600.0


def get_auth_token(token_id: str, token_secret: str, force_refresh: bool = False) -> str:
    global _cached_token, _token_expiry
    now = time.time()
    if not force_refresh and _cached_token and now < (_token_expiry - 120):
        return _cached_token

    params = {
        "TokenID": token_id,
        "TokenSecret": token_secret,
        "IsFromExcel": "false",
    }
    try:
        with httpx.Client(timeout=15.0, verify=SSL_VERIFY) as client:
            resp = client.get(AUTH_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.error("Microvista auth request failed: %s", e)
        raise HTTPException(502, f"Failed to authenticate with Microvista API: {e}")

    token = (data.get("Data") or {}).get("Token") or data.get("Token")
    if not token:
        msg = data.get("Message") or "Token not returned by Microvista"
        raise HTTPException(502, f"Microvista auth error: {msg}")

    _cached_token = token
    _token_expiry = _extract_jwt_exp(token)
    return _cached_token


def _format_address(addr: Dict[str, Any]) -> str:
    parts = []
    for key in ["flno", "bno", "bnm", "st", "loc"]:
        val = (addr.get(key) or "").strip()
        if val and val.lower() not in [p.lower() for p in parts]:
            parts.append(val)
    return ", ".join(parts)[:255]


DEFAULT_TOKEN_ID = "4E622M4X"
DEFAULT_TOKEN_SECRET = "CDEPGKV9TD2T"


def lookup_gstin(gstin: str) -> Dict[str, Any]:
    cleaned = (gstin or "").strip().upper()
    if len(cleaned) != 15:
        raise HTTPException(400, "GSTIN must be exactly 15 characters")
    if not cleaned[:2].isdigit():
        raise HTTPException(400, "GSTIN must start with a 2-digit state code")

    token_id = os.getenv("MICROVISTA_TOKEN_ID", "").strip() or DEFAULT_TOKEN_ID
    token_secret = os.getenv("MICROVISTA_TOKEN_SECRET", "").strip() or DEFAULT_TOKEN_SECRET
    if not token_id or not token_secret:
        raise HTTPException(500, "Microvista API credentials are not configured in MICROVISTA_TOKEN_ID / MICROVISTA_TOKEN_SECRET")

    token = get_auth_token(token_id, token_secret)

    def _call(auth_token: str):
        params = {
            "gstin": cleaned,
            "TokenID": token_id,
            "TokenSecret": token_secret,
            "IsFromExcel": "false",
        }
        headers = {"Authorization": f"Bearer {auth_token}"}
        with httpx.Client(timeout=20.0, verify=SSL_VERIFY) as client:
            return client.get(GSTIN_VERIFY_URL, params=params, headers=headers)

    try:
        resp = _call(token)
        if resp.status_code == 401:
            token = get_auth_token(token_id, token_secret, force_refresh=True)
            resp = _call(token)
        resp.raise_for_status()
        raw = resp.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Microvista GSTIN lookup error for %s: %s", cleaned, e)
        raise HTTPException(502, f"GST verification service error: {e}")

    tp = (raw.get("data") or {}).get("appSCommonSearchTPResponse") or {}
    legal_name = (tp.get("lgnm") or "").strip()
    trade_name = (tp.get("tradeNam") or "").strip()

    if not legal_name and not trade_name:
        raise HTTPException(404, f"GSTIN {cleaned} was not found or has no taxpayer records on file")

    pradr = tp.get("pradr") or {}
    addr = pradr.get("addr") or {}

    city = (addr.get("loc") or addr.get("city") or addr.get("dst") or "").strip()
    state_code = cleaned[:2]
    pin = (addr.get("pncd") or "").strip()[:6]
    pan = cleaned[2:12]
    status = (tp.get("sts") or "Active").strip()
    dty = (tp.get("dty") or "Regular").strip()
    ctb = (tp.get("ctb") or "").strip()
    rgdt = (tp.get("rgdt") or "").strip()
    einvoice_status = (tp.get("einvoiceStatus") or "").strip()

    name = trade_name or legal_name
    bill_addr = _format_address(addr)

    return {
        "gstin": cleaned,
        "name": name,
        "legal_name": legal_name,
        "trade_name": trade_name,
        "party_type": "B2B",
        "bill_addr": bill_addr,
        "bill_city": city[:80],
        "bill_state": state_code,
        "bill_pin": pin,
        "pan": pan,
        "status": status,
        "taxpayer_type": dty,
        "constitution": ctb,
        "registration_date": rgdt,
        "einvoice_status": einvoice_status,
        "raw_address": addr,
    }

