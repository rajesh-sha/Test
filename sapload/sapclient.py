"""The connection to S/4HANA Cloud Public Edition, built to be defensible.

This is the only module that talks to SAP, which is deliberate: there is one
place to review, one place to audit, and one place where the security rules
live.  It uses the standard library, so there is no transitive dependency
chain to vet either.

The rules it enforces, none of which can be switched off:

  * **TLS is verified, always.**  There is no ``verify=False``.  A tool that
    posts to a general ledger does not get an option to trust any certificate.
  * **The host is pinned** to the one in the configuration.  A redirect to
    another host is refused rather than followed — that is how a token walks
    out of the building.
  * **Read-only unless posting was explicitly enabled** for this run.  Any
    write attempt without it raises before a request is made.
  * **Secrets never reach a log.**  Every line written goes through the
    redactor, and payloads are not logged at all by default.
  * **Every call is audited** — who, what, when, status, duration, and a
    correlation id that also goes to SAP so the two logs can be joined.

Failure handling is conservative: bounded retries with exponential backoff on
429 and 5xx only, honouring ``Retry-After``; never a retry on a write that may
already have been applied.
"""

from __future__ import annotations

import base64
import datetime as _dt
import json
import os
import random
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .config import Settings, redact

USER_AGENT = "sapload/0.1 (+https://github.com/rajesh-sha/Test)"
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
TOKEN_MARGIN = 60           # refresh a token a minute before it expires


class SapError(Exception):
    """A call to SAP failed. The message is safe to show a user."""

    def __init__(self, message: str, status: Optional[int] = None,
                 correlation_id: Optional[str] = None):
        super().__init__(message)
        self.status = status
        self.correlation_id = correlation_id


class NotPermitted(SapError):
    """The client was asked to do something this run is not allowed to do."""


@dataclass
class Call:
    """One request, as it will appear in the audit log."""

    when: str
    method: str
    path: str
    status: Optional[int]
    ms: int
    correlation_id: str
    note: str = ""

    def line(self) -> str:
        return (f"{self.when}  {self.method:<6} {self.status or '---':>3}  "
                f"{self.ms:>6}ms  {self.correlation_id}  {self.path}"
                + (f"  {self.note}" if self.note else ""))


class S4Client:
    """A minimal, auditable OData client for S/4HANA Cloud Public Edition."""

    def __init__(self, settings: Settings, audit_sink=None):
        self.settings = settings
        self.calls: List[Call] = []
        self._audit_sink = audit_sink
        self._token: Optional[str] = None
        self._token_expiry: float = 0.0
        self._csrf: Optional[str] = None
        self._cookies: str = ""
        # A default context verifies certificates and checks the hostname.
        # Both are left exactly as the standard library sets them.
        self._ssl = ssl.create_default_context()

    # -- public surface ---------------------------------------------------- #
    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Read one OData collection or entity as JSON."""
        query = dict(params or {})
        query.setdefault("$format", "json")
        body, _headers = self._request("GET", path, query=query)
        try:
            return json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise SapError(f"{path} did not return JSON. Check the service name "
                           f"and that the communication arrangement covers it.")

    def get_all(self, path: str, params: Optional[Dict[str, Any]] = None,
                page: int = 500, cap: int = 20000) -> List[dict]:
        """Page through a collection with ``$top``/``$skip`` up to a hard cap.

        The cap exists so a mistyped filter cannot pull a whole table down and
        trip the tenant's throttling for everyone else.
        """
        out: List[dict] = []
        skip = 0
        while len(out) < cap:
            query = dict(params or {})
            query["$top"] = min(page, cap - len(out))
            query["$skip"] = skip
            payload = self.get(path, query)
            rows = _rows_of(payload)
            out.extend(rows)
            if len(rows) < query["$top"]:
                break
            skip += len(rows)
        return out

    def metadata(self, service_path: str) -> str:
        """Fetch a service's raw $metadata, so field names can be checked.

        This is how a profile stays honest: rather than trusting a field list
        written months ago, ask the tenant what the entity actually has.
        """
        body, _headers = self._request(
            "GET", service_path.rstrip("/") + "/$metadata",
            extra_headers={"Accept": "application/xml"}, note="metadata")
        return body.decode("utf-8", errors="replace")

    def post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create one entity. Refused unless posting was enabled for this run."""
        if not self.settings.allow_post:
            raise NotPermitted(
                "This run is read-only. Posting to SAP requires SAPLOAD_ALLOW_POST=1, "
                "set deliberately by someone who intends to write to the system."
            )
        self._ensure_csrf()
        body, _headers = self._request(
            "POST", path,
            body=json.dumps(payload).encode("utf-8"),
            extra_headers={"Content-Type": "application/json",
                           "X-CSRF-Token": self._csrf or ""},
            retry_safe=False,
        )
        try:
            return json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    def ping(self) -> Tuple[bool, str]:
        """Prove the connection works without reading any business data."""
        try:
            self.get("/sap/opu/odata/sap/API_COMPANYCODE_SRV/A_CompanyCode",
                     {"$top": 1, "$select": "CompanyCode"})
            return True, "Connected. Credentials and network path are good."
        except NotPermitted as exc:
            return False, str(exc)
        except SapError as exc:
            hint = {
                401: "Credentials were rejected. Check the communication user "
                     "and that its password has not expired.",
                403: "Authenticated, but not authorised. The communication "
                     "arrangement probably does not cover this service.",
                404: "Reached the tenant, but the service was not found. Check "
                     "the base URL and that the API is activated.",
            }.get(exc.status or 0, "")
            return False, f"{exc}" + (f" {hint}" if hint else "")

    def audit_report(self) -> str:
        header = (f"# sapload call log · {self.settings.describe()}\n"
                  f"# {len(self.calls)} call(s)\n")
        return header + "\n".join(c.line() for c in self.calls) + "\n"

    # -- authentication ---------------------------------------------------- #
    def _auth_header(self) -> str:
        s = self.settings
        if s.auth == "basic":
            raw = f"{s.username}:{s.password}".encode("utf-8")
            return "Basic " + base64.b64encode(raw).decode("ascii")
        return "Bearer " + self._bearer()

    def _bearer(self) -> str:
        if self._token and time.time() < self._token_expiry - TOKEN_MARGIN:
            return self._token
        s = self.settings
        if s.auth == "oauth_client":
            form = {"grant_type": "client_credentials",
                    "client_id": s.client_id, "client_secret": s.client_secret}
        else:
            form = {"grant_type": "urn:ietf:params:oauth:grant-type:saml2-bearer",
                    "client_id": s.client_id, "assertion": s.assertion}
        data = urllib.parse.urlencode(form).encode("utf-8")
        req = urllib.request.Request(
            s.token_url, data=data, method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=s.timeout, context=self._ssl) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise SapError(f"The token service rejected the request "
                           f"(HTTP {exc.code}). Check the client id and secret.",
                           status=exc.code)
        except urllib.error.URLError as exc:
            raise SapError(f"Could not reach the token service: "
                           f"{redact(str(exc.reason))}")
        token = payload.get("access_token")
        if not token:
            raise SapError("The token service returned no access token.")
        self._token = token
        self._token_expiry = time.time() + float(payload.get("expires_in", 3600))
        return token

    def _ensure_csrf(self) -> None:
        """OData writes need a token fetched by a prior read. Get one, once."""
        if self._csrf:
            return
        _body, headers = self._request(
            "GET", "/sap/opu/odata/sap/API_COMPANYCODE_SRV/",
            extra_headers={"X-CSRF-Token": "Fetch"}, note="csrf fetch")
        self._csrf = headers.get("x-csrf-token")
        cookie = headers.get("set-cookie")
        if cookie:
            self._cookies = "; ".join(part.split(";")[0] for part in cookie.split(", "))
        if not self._csrf:
            raise SapError("SAP did not return a CSRF token, so a write cannot "
                           "be attempted safely.")

    # -- the one place a request is made ----------------------------------- #
    def _request(self, method: str, path: str,
                 query: Optional[Dict[str, Any]] = None,
                 body: Optional[bytes] = None,
                 extra_headers: Optional[Dict[str, str]] = None,
                 retry_safe: bool = True,
                 note: str = "") -> Tuple[bytes, Dict[str, str]]:
        s = self.settings
        if method != "GET" and not s.allow_post:
            raise NotPermitted("This run is read-only.")

        url = s.base_url + ("/" + path.lstrip("/"))
        if query:
            url += "?" + urllib.parse.urlencode(
                {k: v for k, v in query.items() if v is not None}, safe="$,/'")

        # Pin the host. A URL that resolves elsewhere never gets a credential.
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != s.host:
            raise SapError(f"Refusing to send credentials to {parsed.hostname!r} — "
                           f"this client only talks to {s.host!r} over HTTPS.")

        correlation = uuid.uuid4().hex[:16]
        headers = {
            "Authorization": self._auth_header(),
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
            "X-Correlation-ID": correlation,
        }
        if self._cookies:
            headers["Cookie"] = self._cookies
        headers.update(extra_headers or {})

        attempt, delay = 0, 1.0
        while True:
            attempt += 1
            started = time.time()
            status: Optional[int] = None
            try:
                req = _NoRedirect.build(url, method, body, headers)
                opener = urllib.request.build_opener(
                    _NoRedirect(),
                    urllib.request.HTTPSHandler(context=self._ssl),
                )
                with opener.open(req, timeout=s.timeout) as resp:
                    status = resp.status
                    payload = resp.read()
                    got = {k.lower(): v for k, v in resp.headers.items()}
                self._log(method, parsed.path, status, started, correlation, note)
                return payload, got
            except urllib.error.HTTPError as exc:
                status = exc.code
                detail = _sap_message(exc)
                self._log(method, parsed.path, status, started, correlation,
                          note or detail[:80])
                if (status in RETRY_STATUS and retry_safe
                        and attempt <= s.max_retries):
                    time.sleep(_backoff(exc, delay))
                    delay *= 2
                    continue
                raise SapError(_explain(status, detail), status=status,
                               correlation_id=correlation)
            except urllib.error.URLError as exc:
                self._log(method, parsed.path, None, started, correlation, "network")
                if retry_safe and attempt <= s.max_retries:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise SapError(f"Could not reach {s.host}: {redact(str(exc.reason))}",
                               correlation_id=correlation)

    def _log(self, method: str, path: str, status: Optional[int],
             started: float, correlation: str, note: str) -> None:
        call = Call(
            when=_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            method=method, path=redact(path), status=status,
            ms=int((time.time() - started) * 1000),
            correlation_id=correlation, note=redact(note),
        )
        self.calls.append(call)
        if self._audit_sink:
            self._audit_sink(call)
        elif self.settings.audit_path:
            try:
                with open(self.settings.audit_path, "a", encoding="utf-8") as fh:
                    fh.write(call.line() + "\n")
            except OSError:
                pass          # an unwritable log must not stop the work


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Follow no redirects. A 302 to another host is how a token escapes."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

    @staticmethod
    def build(url: str, method: str, body: Optional[bytes],
              headers: Dict[str, str]) -> urllib.request.Request:
        return urllib.request.Request(url, data=body, method=method, headers=headers)


def _backoff(exc: urllib.error.HTTPError, base: float) -> float:
    """Honour Retry-After when SAP sends one; otherwise back off with jitter."""
    retry_after = exc.headers.get("Retry-After") if exc.headers else None
    if retry_after:
        try:
            return min(60.0, float(retry_after))
        except ValueError:
            pass
    return min(30.0, base + random.random())


def _sap_message(exc: urllib.error.HTTPError) -> str:
    try:
        payload = json.loads(exc.read().decode("utf-8"))
    except Exception:
        return ""
    node = payload.get("error", {})
    message = node.get("message")
    if isinstance(message, dict):
        return str(message.get("value", ""))
    return str(message or "")


def _explain(status: int, detail: str) -> str:
    base = {
        400: "SAP rejected the request as malformed.",
        401: "SAP rejected the credentials.",
        403: "Authenticated, but not authorised for that service.",
        404: "That service or entity was not found on this tenant.",
        429: "SAP is throttling this connection.",
    }.get(status, f"SAP returned HTTP {status}.")
    return f"{base} {redact(detail)}".strip()


def _rows_of(payload: Dict[str, Any]) -> List[dict]:
    """Read rows out of either OData V2 ({d:{results}}) or V4 ({value})."""
    if isinstance(payload.get("value"), list):
        return payload["value"]
    d = payload.get("d")
    if isinstance(d, dict) and isinstance(d.get("results"), list):
        return d["results"]
    if isinstance(d, list):
        return d
    return []
