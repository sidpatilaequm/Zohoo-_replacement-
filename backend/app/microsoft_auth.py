import os
from urllib.parse import urlparse

import msal
import base64
import hashlib
import hmac
import json
import time


CLIENT_ID = os.getenv("ENTRA_CLIENT_ID", "").strip()
CLIENT_SECRET = os.getenv("ENTRA_CLIENT_SECRET", "").strip()
TENANT_ID = os.getenv("ENTRA_TENANT_ID", "").strip()
REDIRECT_URI = os.getenv(
    "ENTRA_REDIRECT_URI",
    "http://localhost:8080/api/auth/microsoft/callback",
).strip()
STATE_TTL = 10 * 60  # 10 minutes


def _state_secret() -> bytes:
    secret = os.getenv("SECRET_KEY", "").strip()

    if not secret:
        raise RuntimeError("SECRET_KEY must be configured")

    return secret.encode("utf-8")


def sign_flow(flow: dict) -> str:
    payload = {
        "exp": int(time.time()) + STATE_TTL,
        "flow": flow,
    }

    raw = json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    signature = hmac.new(
        _state_secret(),
        encoded.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()

    return f"{encoded}.{signature}"


def verify_flow(value: str) -> dict:
    try:
        encoded, signature = value.rsplit(".", 1)

        expected = hmac.new(
            _state_secret(),
            encoded.encode("ascii"),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(signature, expected):
            raise ValueError("Invalid signature")

        padding = "=" * (-len(encoded) % 4)

        payload = json.loads(
            base64.urlsafe_b64decode(
                encoded + padding
            ).decode("utf-8")
        )

        if int(payload["exp"]) < int(time.time()):
            raise ValueError("Expired state")

        flow = payload["flow"]

        if not isinstance(flow, dict):
            raise ValueError("Invalid flow")

        return flow

    except Exception as exc:
        raise RuntimeError(
            "Microsoft sign-in state is invalid or expired"
        ) from exc
SCOPES = ["User.Read"]


def configured() -> bool:
    return bool(CLIENT_ID and CLIENT_SECRET and TENANT_ID and REDIRECT_URI)


def authority() -> str:
    return f"https://login.microsoftonline.com/{TENANT_ID}"


def client() -> msal.ConfidentialClientApplication:
    if not configured():
        raise RuntimeError("Microsoft Entra SSO is not configured")

    return msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=authority(),
        client_credential=CLIENT_SECRET,
    )


def start_flow() -> dict:
    return client().initiate_auth_code_flow(
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )


def finish_flow(flow: dict, auth_response: dict) -> dict:
    return client().acquire_token_by_auth_code_flow(
        flow,
        auth_response,
    )


def validate_redirect_uri() -> None:
    parsed = urlparse(REDIRECT_URI)

    if parsed.scheme not in ("http", "https"):
        raise RuntimeError("ENTRA_REDIRECT_URI must use http or https")

    if not parsed.netloc:
        raise RuntimeError("ENTRA_REDIRECT_URI must contain a host")