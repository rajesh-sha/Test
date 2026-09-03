"""Tests for posting documents: what it sends, and what it refuses to send.

The safety properties matter more than the happy path. A duplicate service
order is a real-world problem someone has to unpick by hand, so the guards
against creating one are tested harder than the creation itself.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mock_s4 import MockS4                                          # noqa: E402
from sapload.config import from_env                                 # noqa: E402
from sapload.poster import (ProfileError, S4Client, check,          # noqa: E402
                            entity_properties, load_profile, post, profiles)

SERVICE = "/sap/opu/odata/sap/API_SERVICE_ORDER_SRV"
ORDERS = f"{SERVICE}/A_ServiceOrder"
REF = "ServiceOrderName"

METADATA = """<?xml version="1.0"?>
<edmx:Edmx xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">
 <edmx:DataServices>
  <Schema xmlns="http://schemas.microsoft.com/ado/2008/09/edm">
   <EntityType Name="A_ServiceOrderType">
     <Property Name="ServiceOrder" Type="Edm.String"/>
     <Property Name="ServiceOrderType" Type="Edm.String"/>
     <Property Name="ServiceOrderName" Type="Edm.String"/>
     <Property Name="SoldToParty" Type="Edm.String"/>
   </EntityType>
   <EntityType Name="A_ServiceOrderItemType">
     <Property Name="ServiceOrderItem" Type="Edm.String"/>
     <Property Name="Product" Type="Edm.String"/>
   </EntityType>
  </Schema>
 </edmx:DataServices>
</edmx:Edmx>"""


class TestProfiles(unittest.TestCase):
    def test_service_order_is_available(self):
        self.assertIn("service_order", profiles())

    def test_a_profile_carries_what_to_verify(self):
        self.assertTrue(load_profile("service_order")["verify"])

    def test_an_unknown_profile_lists_the_real_ones(self):
        with self.assertRaises(ProfileError) as c:
            load_profile("nope")
        self.assertIn("service_order", str(c.exception))

    def test_profiles_name_no_field_lists(self):
        """Field names come from the mapping, so a profile cannot go stale."""
        for key, spec in profiles().items():
            self.assertNotIn("fields", spec, key)
            self.assertNotIn("required", spec, key)


class TestMetadataParsing(unittest.TestCase):
    def test_reads_properties_of_one_entity_type(self):
        props = entity_properties(METADATA, "A_ServiceOrderType")
        self.assertEqual(props, {"ServiceOrder", "ServiceOrderType",
                                 "ServiceOrderName", "SoldToParty"})

    def test_does_not_bleed_between_entity_types(self):
        self.assertNotIn("Product", entity_properties(METADATA, "A_ServiceOrderType"))

    def test_an_unknown_entity_type_yields_nothing(self):
        self.assertEqual(entity_properties(METADATA, "A_Nope"), set())


class Live(unittest.TestCase):
    def setUp(self):
        self.mock = MockS4()
        self.mock.metadata_xml = METADATA
        self.mock.collections[ORDERS] = []
        self.addCleanup(self.mock.stop)
        self.profile = load_profile("service_order")
        self.profile["service"] = SERVICE

    def client(self, allow_post=True):
        env = {"SAPLOAD_BASE_URL": self.mock.base_url,
               "SAPLOAD_USERNAME": "COMM_LOADER", "SAPLOAD_PASSWORD": "hunter2"}
        if allow_post:
            env["SAPLOAD_ALLOW_POST"] = "1"
        c = S4Client(from_env(env))
        c._ssl = self.mock.client_ssl_context()
        return c

    def rows(self, n=3):
        return [{"ServiceOrderType": "SVO1", REF: f"WO-{i}", "SoldToParty": "100001"}
                for i in range(1, n + 1)]


class TestChecking(Live):
    def test_all_mapped_fields_exist(self):
        results = check(self.client(), self.profile,
                        ["ServiceOrderType", REF, "SoldToParty"])
        self.assertTrue(all(r.ok for r in results))

    def test_a_field_that_does_not_exist_is_named(self):
        results = check(self.client(), self.profile, ["ServiceOrderType", "NotAField"])
        self.assertFalse(results[0].ok)
        self.assertIn("NotAField", results[0].unknown)

    def test_a_near_miss_gets_a_suggestion(self):
        results = check(self.client(), self.profile, ["SoldToPary"])
        self.assertIn("did you mean 'SoldToParty'", results[0].as_text())

    def test_checking_never_writes(self):
        check(self.client(), self.profile, ["ServiceOrderType"])
        self.assertEqual(self.mock.posted, [])


class TestRefusals(Live):
    def test_posting_without_permission_is_refused(self):
        from sapload.sapclient import NotPermitted
        with self.assertRaises(NotPermitted):
            post(self.client(allow_post=False), self.profile, self.rows(), REF)
        self.assertEqual(self.mock.posted, [])

    def test_a_row_with_no_reference_stops_the_whole_run(self):
        rows = self.rows() + [{"ServiceOrderType": "SVO1", REF: ""}]
        with self.assertRaises(ProfileError) as c:
            post(self.client(), self.profile, rows, REF)
        self.assertIn("unique reference", str(c.exception))
        self.assertEqual(self.mock.posted, [])

    def test_duplicate_references_in_the_source_stop_the_run(self):
        rows = self.rows(2) + [{"ServiceOrderType": "SVO1", REF: "WO-1"}]
        with self.assertRaises(ProfileError) as c:
            post(self.client(), self.profile, rows, REF)
        self.assertIn("more than once", str(c.exception))
        self.assertEqual(self.mock.posted, [])


class TestDryRun(Live):
    def test_dry_run_sends_nothing(self):
        report = post(self.client(), self.profile, self.rows(), REF, dry_run=True)
        self.assertEqual(self.mock.posted, [])
        self.assertEqual(report.count("would-post"), 3)
        self.assertIn("DRY RUN", report.as_text())


class TestPosting(Live):
    def test_posts_one_request_per_document(self):
        report = post(self.client(), self.profile, self.rows(), REF)
        self.assertEqual(report.count("posted"), 3)
        self.assertEqual(len(self.mock.posted), 3)
        self.assertTrue(report.ok)

    def test_returns_the_document_number_sap_created(self):
        report = post(self.client(), self.profile, self.rows(1), REF)
        self.assertTrue(report.results[0].document.startswith("800000"))

    def test_empty_values_are_not_sent(self):
        rows = [{"ServiceOrderType": "SVO1", REF: "WO-9", "SoldToParty": ""}]
        post(self.client(), self.profile, rows, REF)
        self.assertNotIn("SoldToParty", self.mock.posted[0])

    def test_items_are_nested_under_the_navigation_property(self):
        rows = self.rows(1)
        items = {"WO-1": [{"ServiceOrderItem": "10", "Product": "SRV-A"}]}
        post(self.client(), self.profile, rows, REF, item_rows=items)
        self.assertIn("to_Item", self.mock.posted[0])
        self.assertEqual(self.mock.posted[0]["to_Item"][0]["Product"], "SRV-A")

    def test_one_bad_document_does_not_stop_the_others(self):
        self.mock.post_fails_for = {"WO-2"}
        report = post(self.client(), self.profile, self.rows(3), REF)
        self.assertEqual(report.count("posted"), 2)
        self.assertEqual(report.count("failed"), 1)
        self.assertFalse(report.ok)
        self.assertIn("WO-2", report.as_text())


class TestIdempotency(Live):
    """Re-running after a partial failure must not create duplicates."""

    def test_references_already_in_sap_are_skipped(self):
        self.mock.collections[ORDERS] = [
            {REF: "WO-1", "ServiceOrder": "80000001"},
            {REF: "WO-2", "ServiceOrder": "80000002"},
        ]
        report = post(self.client(), self.profile, self.rows(3), REF)
        self.assertEqual(report.count("skipped"), 2)
        self.assertEqual(report.count("posted"), 1)
        self.assertEqual(len(self.mock.posted), 1)

    def test_a_full_re_run_posts_nothing(self):
        self.mock.collections[ORDERS] = [
            {REF: f"WO-{i}", "ServiceOrder": f"8000000{i}"} for i in (1, 2, 3)]
        report = post(self.client(), self.profile, self.rows(3), REF)
        self.assertEqual(report.count("posted"), 0)
        self.assertEqual(self.mock.posted, [])
        self.assertIn("Re-running after a partial failure is safe", report.as_text())

    def test_no_skip_posts_everything_again(self):
        self.mock.collections[ORDERS] = [{REF: "WO-1", "ServiceOrder": "80000001"}]
        report = post(self.client(), self.profile, self.rows(2), REF, skip_existing=False)
        self.assertEqual(report.count("posted"), 2)

    def test_the_verify_notes_reach_the_report(self):
        report = post(self.client(), self.profile, self.rows(1), REF, dry_run=True)
        self.assertTrue(any("Verify:" in n for n in report.notes))


if __name__ == "__main__":
    unittest.main(verbosity=2)
