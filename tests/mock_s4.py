"""A stand-in for an S/4HANA Cloud tenant, served over real HTTPS.

The client refuses plain HTTP and never disables certificate verification, so
testing it honestly means serving TLS and trusting a test certificate in the
test only — not relaxing the client.
"""

from __future__ import annotations

import json
import ssl
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List, Optional


_CERT_CACHE: Optional[tuple] = None


def make_cert() -> tuple:
    """A throwaway self-signed certificate for 127.0.0.1, made once per run."""
    global _CERT_CACHE
    if _CERT_CACHE:
        return _CERT_CACHE
    d = tempfile.mkdtemp(prefix="sapload-cert-")
    cert, key = f"{d}/cert.pem", f"{d}/key.pem"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-keyout", key,
         "-out", cert, "-days", "2", "-nodes", "-subj", "/CN=127.0.0.1",
         "-addext", "subjectAltName=IP:127.0.0.1"],
        check=True, capture_output=True)
    _CERT_CACHE = (cert, key)
    return _CERT_CACHE


class MockS4:
    """Serves canned OData, and records exactly what it was asked for."""

    def __init__(self):
        self.requests: List[dict] = []
        self.collections: Dict[str, List[dict]] = {}
        self.fail_times = 0            # respond 429 this many times, then succeed
        self.redirect_to: Optional[str] = None
        self.csrf = "test-csrf-token-value"
        self.require_auth = True
        self.metadata_xml = ""
        self.posted: List[dict] = []
        self.post_fails_for = set()      # references the tenant should reject
        self.cert, self.key = make_cert()

        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"   # no keep-alive: tests must not hang

            def log_message(self, *a):
                pass

            def _record(self):
                outer.requests.append({
                    "method": self.command, "path": self.path,
                    "headers": {k.lower(): v for k, v in self.headers.items()},
                })

            def _send(self, code, payload=None, headers=None):
                body = json.dumps(payload or {}).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                self._record()
                if self.path.endswith("$metadata"):
                    body = outer.metadata_xml.encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/xml")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if outer.require_auth and "authorization" not in {
                        k.lower() for k in self.headers.keys()}:
                    self._send(401, {"error": {"message": {"value": "no credentials"}}})
                    return
                if outer.redirect_to:
                    self.send_response(302)
                    self.send_header("Location", outer.redirect_to)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if outer.fail_times > 0:
                    outer.fail_times -= 1
                    self._send(429, {"error": {"message": {"value": "throttled"}}},
                               {"Retry-After": "0"})
                    return
                if self.headers.get("X-CSRF-Token") == "Fetch":
                    self._send(200, {}, {"X-CSRF-Token": outer.csrf,
                                         "Set-Cookie": "SAP_SESSIONID=abc; path=/"})
                    return

                path = self.path.split("?")[0]
                rows = outer.collections.get(path)
                if rows is None:
                    self._send(404, {"error": {"message": {"value": "not found"}}})
                    return
                query = dict(
                    part.split("=", 1) for part in self.path.split("?")[-1].split("&")
                    if "=" in part) if "?" in self.path else {}
                top = int(query.get("%24top", query.get("$top", len(rows))))
                skip = int(query.get("%24skip", query.get("$skip", 0)))
                self._send(200, {"d": {"results": rows[skip:skip + top]}})

            def do_POST(self):
                self._record()
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length)
                if self.headers.get("X-CSRF-Token") != outer.csrf:
                    self._send(403, {"error": {"message": {"value": "CSRF token invalid"}}})
                    return
                try:
                    payload = json.loads(raw.decode())
                except ValueError:
                    payload = {}
                outer.posted.append(payload)
                reference = str(payload.get("ServiceOrderName", ""))
                if reference in outer.post_fails_for:
                    self._send(400, {"error": {"message": {"value": "field is not valid"}}})
                    return
                self._send(201, {"d": {"ServiceOrder": f"800000{len(outer.posted):02d}",
                                       "SupplierInvoice": "5105600001"}})

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(self.cert, self.key)
        self._server.socket = ctx.wrap_socket(self._server.socket, server_side=True)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        return f"https://127.0.0.1:{self.port}"

    def client_ssl_context(self) -> ssl.SSLContext:
        """A context that trusts only this mock — verification stays ON."""
        return ssl.create_default_context(cafile=self.cert)

    def stop(self):
        self._server.shutdown()
        self._server.server_close()
