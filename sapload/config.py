"""Where the connection settings come from, and what is refused.

Credentials are read from the environment, never from a file in the repository
and never from an argument on the command line — a command line ends up in
shell history, in process listings and in CI logs.

Every setting is validated on the way in.  The rules that follow are not
configurable, because a tool that posts to a general ledger should not offer a
switch that weakens it:

  * HTTPS only.  A plain http:// host is refused outright.
  * Certificate verification is always on.  There is no flag to turn it off.
  * Read-only unless posting is explicitly enabled, per run, by someone who
    had to type it.
  * A single S/4 host, fixed at start.  Nothing can redirect the client
    somewhere else mid-run.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Optional, Set
from urllib.parse import urlparse

# Never printed, never logged, never written to the reconciliation pack.
SECRET_KEYS = frozenset({
    "SAPLOAD_PASSWORD", "SAPLOAD_CLIENT_SECRET", "SAPLOAD_ASSERTION",
})


class ConfigError(Exception):
    """A setting is missing or unsafe. The message never repeats a secret."""


@dataclass(frozen=True)
class Settings:
    """Everything needed to talk to one S/4HANA Cloud Public Edition tenant."""

    base_url: str
    auth: str                       # "basic" | "oauth_client" | "oauth_saml"
    username: Optional[str] = None
    password: Optional[str] = field(default=None, repr=False)
    client_id: Optional[str] = None
    client_secret: Optional[str] = field(default=None, repr=False)
    token_url: Optional[str] = None
    assertion: Optional[str] = field(default=None, repr=False)
    allow_post: bool = False
    timeout: float = 60.0
    max_retries: int = 3
    audit_path: Optional[str] = None

    @property
    def host(self) -> str:
        return urlparse(self.base_url).hostname or ""

    def describe(self) -> str:
        """A one-line summary safe to print, log or paste into a ticket."""
        who = self.username or self.client_id or "—"
        mode = "READ + POST" if self.allow_post else "read only"
        return (f"{self.host} · auth {self.auth} · as {_mask(who)} · {mode}")

    def __repr__(self) -> str:                      # belt and braces
        return f"Settings({self.describe()})"


def _mask(value: str) -> str:
    """Show enough of an identifier to recognise it, not enough to reuse it."""
    if not value or len(value) <= 4:
        return "****"
    return value[:2] + "*" * (len(value) - 4) + value[-2:]


def redact(text: str) -> str:
    """Strip anything that looks like a credential out of text before it is shown."""
    # Consume the whole value, not just the first token: "Authorization: Bearer
    # <token>" is two tokens, and stopping at the first leaks the second.
    out = re.sub(r"(?i)(authorization\s*[:=]\s*)[^\r\n,}]+", r"\1<redacted>", text)
    out = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+", r"\1<redacted>", out)
    out = re.sub(r"(?i)(basic\s+)[A-Za-z0-9+/=]+", r"\1<redacted>", out)
    out = re.sub(r"(?i)(\"?(?:password|client_secret|access_token|assertion)\"?\s*[:=]\s*\"?)"
                 r"[^\"\s,&}]+", r"\1<redacted>", out)
    out = re.sub(r"(?i)(x-csrf-token\s*[:=]\s*)\S+", r"\1<redacted>", out)
    return out


def from_env(env: Optional[dict] = None, allow_post: Optional[bool] = None) -> Settings:
    """Build settings from the environment, refusing anything unsafe.

    Required:
        SAPLOAD_BASE_URL      https://<tenant>-api.s4hana.cloud.sap

    One of:
        SAPLOAD_USERNAME + SAPLOAD_PASSWORD                 (communication user)
        SAPLOAD_CLIENT_ID + SAPLOAD_CLIENT_SECRET
          + SAPLOAD_TOKEN_URL                               (client credentials)
        SAPLOAD_CLIENT_ID + SAPLOAD_TOKEN_URL
          + SAPLOAD_ASSERTION                               (SAML bearer)

    Optional:
        SAPLOAD_ALLOW_POST=1  SAPLOAD_TIMEOUT  SAPLOAD_AUDIT_LOG
    """
    env = dict(os.environ if env is None else env)

    base_url = (env.get("SAPLOAD_BASE_URL") or "").strip().rstrip("/")
    if not base_url:
        raise ConfigError(
            "SAPLOAD_BASE_URL is not set. Point it at your tenant's API host, "
            "for example https://my123456-api.s4hana.cloud.sap"
        )
    parsed = urlparse(base_url)
    if parsed.scheme != "https":
        raise ConfigError(
            f"SAPLOAD_BASE_URL must start with https:// — refusing to send "
            f"credentials over {parsed.scheme or 'an unknown scheme'}."
        )
    if not parsed.hostname:
        raise ConfigError("SAPLOAD_BASE_URL has no host in it.")

    username = env.get("SAPLOAD_USERNAME")
    password = env.get("SAPLOAD_PASSWORD")
    client_id = env.get("SAPLOAD_CLIENT_ID")
    client_secret = env.get("SAPLOAD_CLIENT_SECRET")
    token_url = (env.get("SAPLOAD_TOKEN_URL") or "").strip() or None
    assertion = env.get("SAPLOAD_ASSERTION")

    if client_id and token_url and assertion:
        auth = "oauth_saml"
    elif client_id and token_url and client_secret:
        auth = "oauth_client"
    elif username and password:
        auth = "basic"
    else:
        raise ConfigError(
            "No usable credentials. Set either SAPLOAD_USERNAME and "
            "SAPLOAD_PASSWORD for a communication user, or SAPLOAD_CLIENT_ID "
            "with SAPLOAD_TOKEN_URL and either SAPLOAD_CLIENT_SECRET or "
            "SAPLOAD_ASSERTION for OAuth."
        )

    if token_url and urlparse(token_url).scheme != "https":
        raise ConfigError("SAPLOAD_TOKEN_URL must start with https://")

    if allow_post is None:
        allow_post = env.get("SAPLOAD_ALLOW_POST", "").strip() in ("1", "true", "yes")

    try:
        timeout = float(env.get("SAPLOAD_TIMEOUT", "60"))
    except ValueError:
        raise ConfigError("SAPLOAD_TIMEOUT must be a number of seconds.")
    if not 1 <= timeout <= 600:
        raise ConfigError("SAPLOAD_TIMEOUT must be between 1 and 600 seconds.")

    return Settings(
        base_url=base_url, auth=auth, username=username, password=password,
        client_id=client_id, client_secret=client_secret, token_url=token_url,
        assertion=assertion, allow_post=bool(allow_post), timeout=timeout,
        audit_path=env.get("SAPLOAD_AUDIT_LOG") or None,
    )


def missing_settings(env: Optional[dict] = None) -> Set[str]:
    """Which required variables are absent — for a helpful message, not a stack."""
    env = dict(os.environ if env is None else env)
    missing = set()
    if not env.get("SAPLOAD_BASE_URL"):
        missing.add("SAPLOAD_BASE_URL")
    has_basic = env.get("SAPLOAD_USERNAME") and env.get("SAPLOAD_PASSWORD")
    has_oauth = env.get("SAPLOAD_CLIENT_ID") and env.get("SAPLOAD_TOKEN_URL") and (
        env.get("SAPLOAD_CLIENT_SECRET") or env.get("SAPLOAD_ASSERTION"))
    if not (has_basic or has_oauth):
        missing.add("SAPLOAD_USERNAME + SAPLOAD_PASSWORD (or the OAuth trio)")
    return missing
