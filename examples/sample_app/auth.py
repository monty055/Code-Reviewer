"""User authentication for the Task Tracker API."""

import hashlib
import hmac
import secrets
import time

_MAX_FAILED_ATTEMPTS = 5
_failed_attempts: dict[str, int] = {}
_locked_until: dict[str, float] = {}

_SECRET_KEY = secrets.token_bytes(32)


def hash_password(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000).hex()


def is_account_locked(email: str) -> bool:
    locked_until = _locked_until.get(email)
    return locked_until is not None and time.time() < locked_until


def login(email: str, password: str, stored_hash: str, salt: bytes) -> str | None:
    """Attempt to log a user in. Returns a signed auth token on success, or
    None if the credentials are invalid or the account is locked."""

    if is_account_locked(email):
        return None

    candidate_hash = hash_password(password, salt)
    if not hmac.compare_digest(candidate_hash, stored_hash):
        _failed_attempts[email] = _failed_attempts.get(email, 0) + 1
        if _failed_attempts[email] >= _MAX_FAILED_ATTEMPTS:
            _locked_until[email] = time.time() + 15 * 60
        return None

    _failed_attempts[email] = 0
    return _issue_token(email)


def _issue_token(email: str) -> str:
    payload = f"{email}:{int(time.time())}"
    signature = hmac.new(_SECRET_KEY, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"
