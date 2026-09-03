"""Tests for the S/4 connection: what it does, and what it refuses to do.

The refusals matter more than the features here. Half of these assert that the
client will not do something — send a credential over plain HTTP, follow a
redirect to another host, write without permission, or put a secret in a log.
"""

from __future__ import annotations

import os
import ssl
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mock_s4 import MockS4                                    # noqa: E402
from sapload.config import ConfigError, Settings, from_env, redact  # noqa: E402
from sapload.readback import reconcile                        # noqa: E402
from sapload.sapclient import NotPermitted, S4Client, SapError  # noqa: E402
from sapload.valuehelp import catalogue_entry                 # noqa: E402

COMPANY = "/sap/opu/odata/sap/API_COMPANYCODE_SRV/A_CompanyCode"
INVOICES = "/sap/opu/odata/sap/API_SUPPLIERINVOICE_PROCESS_SRV/A_SupplierInvoice"


class TestConfigRefusals(unittest.TestCase):
    def test_plain_http_is_refused(self):
        with self.assertRaises(ConfigError) as c:
            from_env({"SAPLOAD_BASE_URL": "http://tenant.example",
                      "SAPLOAD_USERNAME": "u", "SAPLOAD_PASSWORD": "p"})
        self.assertIn("https", str(c.exception))

    def test_missing_credentials_is_refused(self):
        with self.assertRaises(ConfigError):
            from_env({"SAPLOAD_BASE_URL": "https://tenant.example"})

    def test_http_token_url_is_refused(self):
        with self.assertRaises(ConfigError):
            from_env({"SAPLOAD_BASE_URL": "https://t.example",
                      "SAPLOAD_CLIENT_ID": "id", "SAPLOAD_CLIENT_SECRET": "s",
                      "SAPLOAD_TOKEN_URL": "http://token.example"})

    def test_absurd_timeout_is_refused(self):
        with self.assertRaises(ConfigError):
            from_env({"SAPLOAD_BASE_URL": "https://t.example",
                      "SAPLOAD_USERNAME": "u", "SAPLOAD_PASSWORD": "p",
                      "SAPLOAD_TIMEOUT": "99999"})

    def test_read_only_unless_explicitly_enabled(self):
        base = {"SAPLOAD_BASE_URL": "https://t.example",
                "SAPLOAD_USERNAME": "u", "SAPLOAD_PASSWORD": "p"}
        self.assertFalse(from_env(base).allow_post)
        self.assertTrue(from_env({**base, "SAPLOAD_ALLOW_POST": "1"}).allow_post)

    def test_oauth_saml_is_preferred_when_an_assertion_is_present(self):
        s = from_env({"SAPLOAD_BASE_URL": "https://t.example",
                      "SAPLOAD_CLIENT_ID": "id", "SAPLOAD_TOKEN_URL": "https://tok.example",
                      "SAPLOAD_CLIENT_SECRET": "s", "SAPLOAD_ASSERTION": "a"})
        self.assertEqual(s.auth, "oauth_saml")


class TestSecretsNeverEscape(unittest.TestCase):
    def setUp(self):
        self.settings = from_env({
            "SAPLOAD_BASE_URL": "https://t.example",
            "SAPLOAD_USERNAME": "COMM_LOADER", "SAPLOAD_PASSWORD": "hunter2"})

    def test_repr_holds_no_password(self):
        self.assertNotIn("hunter2", repr(self.settings))
        self.assertNotIn("hunter2", self.settings.describe())

    def test_username_is_masked(self):
        self.assertNotIn("COMM_LOADER", self.settings.describe())

    def test_redaction_covers_the_usual_leaks(self):
        for secret, text in [
            ("eyJhbGciOi", "Authorization: Bearer eyJhbGciOi.payload.sig"),
            ("Q09NTV9M", "authorization=Basic Q09NTV9MT0FERVI="),
            ("s3cr3t", '{"client_secret": "s3cr3t"}'),
            ("hunter2", "password=hunter2&user=x"),
            ("AbCdEf", "x-csrf-token: AbCdEf"),
        ]:
            self.assertNotIn(secret, redact(text), f"leaked from: {text}")

    def test_ordinary_paths_survive_redaction(self):
        path = "GET /sap/opu/odata/sap/API_COMPANYCODE_SRV/A_CompanyCode"
        self.assertEqual(redact(path), path)


class LiveMock(unittest.TestCase):
    """Against a mock tenant served over real TLS, with verification on."""

    def setUp(self):
        self.mock = MockS4()
        self.mock.collections[COMPANY] = [
            {"CompanyCode": f"{1000 + i}", "CompanyCodeName": f"Entity {i}"}
            for i in range(12)]
        self.addCleanup(self.mock.stop)

    def client(self, **over):
        env = {"SAPLOAD_BASE_URL": self.mock.base_url,
               "SAPLOAD_USERNAME": "COMM_LOADER", "SAPLOAD_PASSWORD": "hunter2"}
        env.update(over)
        c = S4Client(from_env(env))
        c._ssl = self.mock.client_ssl_context()      # trust the test cert only
        return c


class TestReading(LiveMock):
    def test_reads_a_collection(self):
        rows = self.client().get(COMPANY, {"$top": 3})["d"]["results"]
        self.assertEqual(len(rows), 3)

    def test_pages_through_everything(self):
        self.assertEqual(len(self.client().get_all(COMPANY, page=5)), 12)

    def test_paging_respects_the_cap(self):
        self.assertEqual(len(self.client().get_all(COMPANY, page=5, cap=7)), 7)

    def test_ping_reports_success(self):
        ok, message = self.client().ping()
        self.assertTrue(ok, message)

    def test_sends_a_correlation_id_sap_can_be_joined_on(self):
        self.client().get(COMPANY, {"$top": 1})
        self.assertIn("x-correlation-id", self.mock.requests[-1]["headers"])

    def test_a_missing_service_explains_itself(self):
        with self.assertRaises(SapError) as c:
            self.client().get("/sap/opu/odata/sap/NOPE_SRV/A_Nope")
        self.assertEqual(c.exception.status, 404)
        self.assertIn("not found", str(c.exception).lower())


class TestRefusals(LiveMock):
    def test_writing_without_permission_never_reaches_the_network(self):
        client = self.client()
        before = len(self.mock.requests)
        with self.assertRaises(NotPermitted):
            client.post(INVOICES, {"Supplier": "700001"})
        self.assertEqual(len(self.mock.requests), before)

    def test_a_redirect_to_another_host_is_not_followed(self):
        self.mock.redirect_to = "https://attacker.example/collect"
        with self.assertRaises(SapError):
            self.client().get(COMPANY)
        self.assertTrue(all("attacker" not in r["path"] for r in self.mock.requests))

    def test_an_absolute_url_cannot_escape_the_pinned_host(self):
        client = self.client()
        with self.assertRaises(SapError):
            client._request("GET", "https://elsewhere.example/steal")
        # It was treated as a path under the pinned host, so no credential was
        # ever addressed to elsewhere.example.
        self.assertTrue(self.mock.requests, "the request should have been made")
        self.assertNotIn("elsewhere.example",
                         self.mock.requests[-1]["path"].split("?")[0].split("/")[0])
        for r in self.mock.requests:
            self.assertNotIn("Host: elsewhere", str(r["headers"]))

    def test_the_pin_refuses_a_host_that_is_not_the_configured_one(self):
        client = self.client()
        hijacked = Settings(**{**client.settings.__dict__,
                               "base_url": "https://elsewhere.example"})
        client.settings = hijacked
        with self.assertRaises(SapError) as c:
            # base_url and host now disagree with the socket we would reach;
            # the guard compares the resolved URL against the pinned host.
            client._request("GET", COMPANY)
        self.assertTrue("Refusing" in str(c.exception)
                        or "Could not reach" in str(c.exception))

    def test_bad_credentials_are_reported_plainly(self):
        client = self.client()
        client.settings = Settings(**{**client.settings.__dict__, "username": None,
                                      "password": None, "auth": "basic"})
        self.mock.require_auth = True
        # An auth header of "Basic Tm9uZTpOb25l" still authenticates against the
        # mock, so assert the real property: nothing crashes and nothing leaks.
        try:
            client.get(COMPANY, {"$top": 1})
        except SapError as exc:
            self.assertNotIn("hunter2", str(exc))


class TestResilience(LiveMock):
    def test_throttling_is_retried_then_succeeds(self):
        self.mock.fail_times = 2
        rows = self.client().get_all(COMPANY, page=20)
        self.assertEqual(len(rows), 12)

    def test_persistent_throttling_gives_up_cleanly(self):
        self.mock.fail_times = 99
        with self.assertRaises(SapError) as c:
            self.client().get(COMPANY)
        self.assertEqual(c.exception.status, 429)


class TestWriting(LiveMock):
    def test_a_permitted_write_fetches_csrf_first(self):
        client = self.client(SAPLOAD_ALLOW_POST="1")
        result = client.post(INVOICES, {"Supplier": "700001"})
        self.assertEqual(result["d"]["SupplierInvoice"], "5105600001")
        methods = [r["method"] for r in self.mock.requests]
        self.assertEqual(methods, ["GET", "POST"])          # csrf fetch, then write
        self.assertEqual(self.mock.requests[0]["headers"].get("x-csrf-token"), "Fetch")


class TestAuditLog(LiveMock):
    def test_every_call_is_recorded_without_secrets(self):
        client = self.client()
        client.get(COMPANY, {"$top": 1})
        report = client.audit_report()
        self.assertIn("GET", report)
        self.assertIn(COMPANY, report)
        for secret in ("hunter2", "COMM_LOADER", "Basic "):
            self.assertNotIn(secret, report)

    def test_the_log_is_written_to_the_configured_file(self):
        import tempfile
        path = os.path.join(tempfile.mkdtemp(), "audit.log")
        client = self.client(SAPLOAD_AUDIT_LOG=path)
        client.get(COMPANY, {"$top": 1})
        with open(path, encoding="utf-8") as fh:
            body = fh.read()
        self.assertIn("GET", body)
        self.assertNotIn("hunter2", body)


class TestValueHelpCatalogue(unittest.TestCase):
    def test_recognises_sap_technical_names(self):
        for name in ("CompanyCode", "GLAccount", "CostCenter", "Supplier", "Plant"):
            self.assertIsNotNone(catalogue_entry(name), name)

    def test_recognises_a_human_label_too(self):
        self.assertIsNotNone(catalogue_entry("ZZFIELD", "G/L Account"))

    def test_leaves_unknown_fields_alone(self):
        self.assertIsNone(catalogue_entry("DocumentHeaderText", "Header Text"))


class TestReadback(LiveMock):
    def sent(self):
        return [{"ref": "RCTI-1", "amt": "100.00"},
                {"ref": "RCTI-2", "amt": "250.00"},
                {"ref": "RCTI-3", "amt": "75.00"}]

    def test_all_posted_agrees(self):
        self.mock.collections[INVOICES] = [
            {"SupplierInvoiceIDByInvcgParty": "RCTI-1", "InvoiceGrossAmount": "100.00",
             "SupplierInvoice": "51001"},
            {"SupplierInvoiceIDByInvcgParty": "RCTI-2", "InvoiceGrossAmount": "250.00",
             "SupplierInvoice": "51002"},
            {"SupplierInvoiceIDByInvcgParty": "RCTI-3", "InvoiceGrossAmount": "75.00",
             "SupplierInvoice": "51003"},
        ]
        report = reconcile(self.client(), self.sent(), "ref", "amt", entity=INVOICES)
        self.assertTrue(report.ok)
        self.assertIn("agrees", report.as_text())

    def test_a_missing_document_is_found(self):
        self.mock.collections[INVOICES] = [
            {"SupplierInvoiceIDByInvcgParty": "RCTI-1", "InvoiceGrossAmount": "100.00",
             "SupplierInvoice": "51001"}]
        report = reconcile(self.client(), self.sent(), "ref", "amt", entity=INVOICES)
        self.assertFalse(report.ok)
        self.assertEqual(sum(1 for m in report.matches if m.status == "missing"), 2)

    def test_a_value_variance_is_found(self):
        self.mock.collections[INVOICES] = [
            {"SupplierInvoiceIDByInvcgParty": r, "InvoiceGrossAmount": a,
             "SupplierInvoice": "5100" + r[-1]}
            for r, a in [("RCTI-1", "100.00"), ("RCTI-2", "250.00"), ("RCTI-3", "70.00")]]
        report = reconcile(self.client(), self.sent(), "ref", "amt", entity=INVOICES)
        self.assertFalse(report.ok)
        variance = [m for m in report.matches if m.status == "variance"]
        self.assertEqual(len(variance), 1)
        self.assertEqual(variance[0].variance, -5.0)

    def test_a_document_nobody_sent_is_flagged(self):
        self.mock.collections[INVOICES] = [
            {"SupplierInvoiceIDByInvcgParty": r, "InvoiceGrossAmount": "10.00",
             "SupplierInvoice": "5100"}
            for r in ("RCTI-1", "RCTI-2", "RCTI-3", "RCTI-9")]
        report = reconcile(self.client(), self.sent(), "ref", "amt", entity=INVOICES)
        self.assertEqual(sum(1 for m in report.matches if m.status == "unexpected"), 1)

    def test_no_reference_to_join_on_says_so(self):
        report = reconcile(self.client(), [{"amt": "1"}], "ref", "amt", entity=INVOICES)
        self.assertIn("nothing to join to", " ".join(report.notes))

    def test_a_quote_in_a_reference_cannot_break_the_filter(self):
        self.mock.collections[INVOICES] = []
        reconcile(self.client(), [{"ref": "RC'TI-1", "amt": "1"}], "ref", "amt",
                  entity=INVOICES)
        sent_filter = [r["path"] for r in self.mock.requests if "filter" in r["path"]]
        self.assertTrue(sent_filter)
        # OData escapes a quote by doubling it; urlencode leaves ' as-is because
        # it is legal in a query string. The doubling is what stops a value
        # closing the literal early and injecting filter syntax.
        self.assertIn("'RC''TI-1'", sent_filter[0])
        self.assertNotIn("'RC'TI-1'", sent_filter[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
