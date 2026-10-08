"""Fixed-domain read-only Google adapter. No provider payloads in exceptions/logs."""

import base64
import json
import math
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken

MAILBOX = "aban.hackathon@gmail.com"
SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


FAILURE_CODES = {
    "authorization_changed",
    "connection_changed",
    "consent_denied",
    "invalid_checkpoint",
    "invalid_provider_response",
    "processing_failed",
    "provider_timeout",
    "scan_limit",
    "stale_lease",
    "state_invalid",
    "invalid_attachment",
    "key_unavailable",
    "provider_response_size",
    "provider_unavailable",
    "permission_denied",
    "quota_exceeded",
    "refresh_missing",
    "revoked",
    "scope_missing",
    "wrong_account",
    "storage_limit",
}


class GmailFailure(Exception):
    def __init__(self, code, transient=False):
        self.code = code if code in FAILURE_CODES else "processing_failed"
        self.transient = transient
        super().__init__(self.code)


@dataclass(frozen=True, repr=False)
class GmailSettings:
    client_id: str
    client_secret: str
    callback: str
    key_version: str
    keys: dict

    @classmethod
    def load(cls, values, origin):
        names = (
            "GOOGLE_CLIENT_ID",
            "GOOGLE_CLIENT_SECRET",
            "GMAIL_TOKEN_KEY_VERSION",
            "GMAIL_TOKEN_KEYS",
        )
        if not all(values.get(name) for name in names):
            return None
        try:
            keys = json.loads(values["GMAIL_TOKEN_KEYS"])
            if not isinstance(keys, dict) or not 1 <= len(keys) <= 3:
                raise ValueError
            for version, key in keys.items():
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", version):
                    raise ValueError
                Fernet(key.encode())
            current = values["GMAIL_TOKEN_KEY_VERSION"]
            if current not in keys:
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise ValueError("Invalid Gmail encryption key configuration") from None
        return cls(
            values["GOOGLE_CLIENT_ID"],
            values["GOOGLE_CLIENT_SECRET"],
            origin + "/auth/google/callback",
            current,
            keys,
        )

    def encrypt(self, tokens):
        return Fernet(self.keys[self.key_version].encode()).encrypt(json.dumps(tokens).encode())

    def decrypt(self, ciphertext, version):
        try:
            result = json.loads(Fernet(self.keys[version].encode()).decrypt(ciphertext))
            if not isinstance(result, dict):
                raise ValueError
            for field in ("access_token", "refresh_token"):
                if not isinstance(result.get(field), str) or not 1 <= len(result[field]) <= 8192:
                    raise ValueError
            expiry = result.get("expires_at")
            if (
                isinstance(expiry, bool)
                or not isinstance(expiry, (int, float))
                or not math.isfinite(expiry)
                or not 0 <= expiry <= 4102444800
            ):
                raise ValueError
            return result
        except (KeyError, InvalidToken, ValueError, TypeError):
            raise GmailFailure("key_unavailable") from None


class GoogleAdapter:
    def __init__(self, settings):
        self.settings = settings

    def authorization_url(self, state):
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
            {
                "client_id": self.settings.client_id,
                "redirect_uri": self.settings.callback,
                "response_type": "code",
                "scope": SCOPE,
                "access_type": "offline",
                "prompt": "consent",
                "state": state,
            }
        )

    def request(self, method, url, *, token=None, data=None, params=None, limit=2 * 1024 * 1024):
        # Destinations are constants assembled only by this adapter; redirects never followed.
        deadline = time.monotonic() + 15
        try:
            with httpx.Client(
                timeout=httpx.Timeout(10, connect=5), follow_redirects=False
            ) as client:
                with client.stream(
                    method,
                    url,
                    headers={"Authorization": "Bearer " + token} if token else {},
                    data=data,
                    params=params,
                ) as response:
                    if response.status_code >= 400:
                        if response.status_code in {401, 400}:
                            raise GmailFailure("revoked")
                        if response.status_code in {403, 429}:
                            raise GmailFailure(
                                "quota_exceeded"
                                if response.status_code == 429
                                else "permission_denied",
                                response.status_code == 429,
                            )
                        raise GmailFailure("provider_unavailable", response.status_code >= 500)
                    if response.status_code != 200:
                        raise GmailFailure("invalid_provider_response")
                    chunks, size = [], 0
                    for chunk in response.iter_bytes():
                        if time.monotonic() > deadline:
                            raise GmailFailure("provider_timeout", True)
                        size += len(chunk)
                        if size > limit:
                            raise GmailFailure("provider_response_size")
                        chunks.append(chunk)
                    result = json.loads(b"".join(chunks)) if chunks else {}
                    if not isinstance(result, dict):
                        raise ValueError
                    return result
        except GmailFailure:
            raise
        except httpx.TimeoutException:
            raise GmailFailure("provider_timeout", True) from None
        except httpx.HTTPError:
            raise GmailFailure("provider_unavailable", True) from None
        except (ValueError, TypeError):
            raise GmailFailure("invalid_provider_response") from None

    def tokens(self, *, code=None, refresh=None):
        data = {"client_id": self.settings.client_id, "client_secret": self.settings.client_secret}
        if code is not None:
            data.update(
                grant_type="authorization_code", code=code, redirect_uri=self.settings.callback
            )
        else:
            data.update(grant_type="refresh_token", refresh_token=refresh)
        result = self.request("POST", "https://oauth2.googleapis.com/token", data=data)
        try:
            if (
                result.get("token_type", "").lower() != "bearer"
                or not isinstance(result["access_token"], str)
                or not 1 <= len(result["access_token"]) <= 8192
            ):
                raise ValueError
            if code is not None and SCOPE not in result.get("scope", "").split():
                raise GmailFailure("scope_missing")
            ttl = int(result["expires_in"])
            if not 1 <= ttl <= 86400:
                raise ValueError
            refresh_token = result.get("refresh_token") or refresh
            if not isinstance(refresh_token, str) or not 1 <= len(refresh_token) <= 8192:
                raise GmailFailure("refresh_missing")
            return {
                "access_token": result["access_token"],
                "refresh_token": refresh_token,
                "expires_at": datetime.now(UTC).timestamp() + ttl,
            }
        except (ValueError, KeyError, TypeError):
            raise GmailFailure("invalid_provider_response") from None

    def profile(self, token):
        result = self.request(
            "GET", "https://gmail.googleapis.com/gmail/v1/users/me/profile", token=token
        )
        if result.get("emailAddress", "").lower() != MAILBOX:
            raise GmailFailure("wrong_account")
        return MAILBOX

    def messages(self, token, start, end):
        query = (
            f"after:{int(start.timestamp()) - 1} before:{int(end.timestamp())} "
            "has:attachment {receipt invoice booking ticket}"
        )
        result = self.request(
            "GET",
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            token=token,
            params={"q": query, "maxResults": 15},
        )
        items = result.get("messages", [])
        if not isinstance(items, list) or len(items) > 15:
            raise GmailFailure("invalid_provider_response")
        ids = [self.identifier(item.get("id")) for item in items if isinstance(item, dict)]
        if len(ids) != len(items) or len(set(ids)) != len(ids):
            raise GmailFailure("invalid_provider_response")
        if any(len(id) > 200 for id in ids):
            raise GmailFailure("invalid_provider_response")
        return ids, bool(result.get("nextPageToken"))

    @staticmethod
    def identifier(value):
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,512}", value):
            raise GmailFailure("invalid_provider_response")
        return value

    def message(self, token, id):
        id = self.identifier(id)
        result = self.request(
            "GET",
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{id}",
            token=token,
            params={"format": "full"},
            limit=56 * 1024 * 1024 + 1024 * 1024,
        )
        try:
            if result.get("id") != id:
                raise ValueError
            received = datetime.fromtimestamp(int(result["internalDate"]) / 1000, UTC)
            parts, pending = [], [result["payload"]]
            for _ in range(100):
                if not pending:
                    break
                part = pending.pop()
                if not isinstance(part, dict) or not isinstance(part.get("parts", []), list):
                    raise ValueError
                pending.extend(part.get("parts", []))
                if part.get("filename"):
                    body = part.get("body", {})
                    try:
                        identity = body.get("attachmentId")
                        extra = {}
                        if identity:
                            identity = self.identifier(identity)
                        else:
                            part_id = part.get("partId")
                            if (
                                not isinstance(part_id, str)
                                or len(part_id) > 128
                                or not re.fullmatch(r"(?:[0-9]+(?:\.[0-9]+)*)?", part_id)
                            ):
                                raise ValueError
                            identity = "inline:" + (part_id or "root")
                            extra = {"data": body.get("data")}
                        size = int(body.get("size", 0))
                    except (GmailFailure, ValueError, TypeError, AttributeError):
                        identity, size, extra = f"invalid:{len(parts)}", 0, {}
                    parts.append(
                        {
                            "id": identity,
                            "name": str(part["filename"])[:512],
                            "mime": part.get("mimeType"),
                            "size": size,
                            **extra,
                        }
                    )
            if pending or len(parts) > 50:
                raise ValueError
            return received, parts
        except (ValueError, KeyError, TypeError, OverflowError, OSError):
            raise GmailFailure("invalid_provider_response") from None

    def attachment(self, token, message, attachment):
        message, attachment = self.identifier(message), self.identifier(attachment)
        result = self.request(
            "GET",
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message}/attachments/{attachment}",
            token=token,
            limit=14 * 1024 * 1024 + 1024,
        )
        return decode_attachment(result.get("data"), result.get("size"))

    def revoke(self, token):
        # Google may return an empty JSON object; revocation failures remain distinguishable.
        self.request("POST", "https://oauth2.googleapis.com/revoke", data={"token": token})


def decode_attachment(value, size):
    """The same bounded strict decoder for external and inline named MIME parts."""
    try:
        if not isinstance(value, str) or len(value) > 14 * 1024 * 1024:
            raise ValueError
        content = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        if len(content) != int(size) or not 0 < len(content) <= 10 * 1024 * 1024:
            raise ValueError
        return content
    except (ValueError, TypeError):
        raise GmailFailure("invalid_attachment") from None
