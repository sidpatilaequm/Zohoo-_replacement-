"""Password hashing and bearer tokens, using only the standard library.

PBKDF2-HMAC-SHA256 for passwords and an HMAC-signed token for sessions.
Both are standard constructions; the point of writing them out rather than
pulling in a library is that there is nothing hidden here to audit.
"""
import base64, hashlib, hmac, json, os, secrets, time

SECRET = os.getenv("SECRET_KEY", "dev-only-change-me").encode()
ITERATIONS = 240_000
TOKEN_TTL = int(os.getenv("TOKEN_TTL_SECONDS", "43200"))   # 12 hours


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, dk_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(),
                                 base64.b64decode(salt_b64), int(iters))
        return hmac.compare_digest(dk, base64.b64decode(dk_b64))
    except Exception:
        return False


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def make_token(user_id: int, tenant_id: int | None) -> str:
    payload = {"uid": user_id, "tid": tenant_id, "exp": int(time.time()) + TOKEN_TTL}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64(hmac.new(SECRET, body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def read_token(tok: str) -> dict | None:
    try:
        body, sig = tok.split(".")
        expect = _b64(hmac.new(SECRET, body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expect):
            return None
        payload = json.loads(_unb64(body))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None
