# Security model

This tool touches a production general ledger. The controls below are properties
of the code, not settings — there is no flag that turns any of them off.

## What connects, and what does not

| Component | Talks to SAP | Holds credentials |
|---|---|---|
| `SAP-Load-Workbench.html` (browser) | **No** | **No** |
| `sapload.serve` (local web app) | No | No |
| `sapload` CLI, mapping and validation | No | No |
| `sapload.sapclient` | Yes | Yes, in memory only |

The default path — read a template, map an extract, produce a file a person
uploads — never connects to SAP at all. That is deliberate: it keeps the tool
out of scope for interface controls, and keeps a human at the point of posting.

## The rules the client enforces

**TLS is verified, always.** There is no `verify=False` and no option to add
one. A plain `http://` base URL or token URL is refused at configuration time,
before any credential is read.

**The host is pinned.** Every request is checked against the configured host
before a credential is attached. Redirects are not followed — a 302 to another
host is exactly how a bearer token leaves the building, so `_NoRedirect`
returns `None` rather than chasing it.

**Read-only unless a human enabled writing.** `SAPLOAD_ALLOW_POST=1` must be
set for this run. Without it a write raises *before a socket is opened*, so a
mistake cannot become a posting. Tested: `test_writing_without_permission_never_reaches_the_network`.

**Credentials come only from the environment.** Never from a file in the
repository, never from a command-line argument — an argument appears in shell
history, in `ps`, and in CI logs.

**Secrets never reach a log.** Every logged string passes through `redact()`,
which covers `Authorization` headers (whole value, not just the scheme),
bearer and basic tokens, `client_secret`, `password`, `access_token`,
`assertion` and CSRF tokens. `Settings.__repr__` is overridden so a stack trace
or a debugger cannot print a password. Usernames are masked. Request and
response bodies are not logged at all.

**Every call is audited.** Timestamp, method, path, status, duration and a
correlation id that is also sent to SAP as `X-Correlation-ID`, so the two logs
can be joined during an investigation. Write it to a file with
`SAPLOAD_AUDIT_LOG`.

**Failures are handled conservatively.** Bounded retries with exponential
backoff and jitter, on 429 and 5xx only, honouring `Retry-After`. A write is
never retried — a timeout on a POST may mean the document posted, and a blind
retry is how a duplicate journal entry is created.

**Filter values are escaped.** References going into an OData `$filter` have
quotes doubled per the OData rule, so a value cannot close the literal and
inject filter syntax.

**Paging is capped.** `get_all` stops at a hard limit so a mistyped filter
cannot pull an entire table and trip the tenant's throttling for everyone else.

## Choosing an authentication method

| Method | When | Audit quality |
|---|---|---|
| **OAuth 2.0 SAML Bearer** | **Preferred.** Principal propagation — the named business user's identity reaches SAP | Best: SAP authorisations and audit apply per person |
| OAuth 2.0 client credentials | Service-to-service, scheduled runs | A technical user, so SAP sees the service, not the person |
| Basic auth, communication user | Getting started, and read-only scopes | Weakest: shared credential, rotate it deliberately |

For finance postings, use SAML bearer. A shared technical user posting revenue
is a finding waiting to happen, and it is much harder to argue after the fact
than before.

## Least privilege

Create a **separate communication user for read-only use**, scoped to the
reference-data and read APIs only. Value help and reconciliation need nothing
more. Keep the posting arrangement separate, so the credential that runs the
weekly reconciliation cannot write to the ledger even if it leaks.

Scope the communication arrangement to the specific services in use. A
scenario that covers more than the tool calls is standing access nobody
reviews.

## Operational notes

- The local web app binds to `127.0.0.1` by default. `--host 0.0.0.0` exposes
  it to the network; only do that behind an authenticating proxy.
- Uploaded files live in a temporary directory for one session and are
  discarded. Nothing is persisted server-side.
- The browser build stores confirmed mappings in `localStorage`. That is
  mapping metadata — field names — not business data.
- Rotate the communication user's password on the schedule your policy sets.
  There is no credential caching to clear.

## What this does not do

No secrets management: it reads the environment and expects the platform to
have put the right values there — BTP destination service, Azure Key Vault,
or your CI's secret store. It does not encrypt anything at rest, because it
stores nothing at rest.

## Reporting a problem

Raise it privately with the repository owner before opening an issue.
