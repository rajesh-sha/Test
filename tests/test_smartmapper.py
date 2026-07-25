"""Test suite for smartmapper. Run with: python -m pytest  (or python -m unittest)."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smartmapper import SmartFieldMapper, MappingMemory, profile_column  # noqa: E402
from smartmapper import similarity, text, knowledge  # noqa: E402
from smartmapper.profiling import profile_similarity, type_hint_from_name  # noqa: E402
from smartmapper.transforms import (  # noqa: E402
    get_transform,
    infer_dayfirst,
    make_iso_date_transform,
    suggest_transform,
)


class TestText(unittest.TestCase):
    def test_normalize_camel_and_symbols(self):
        self.assertEqual(text.normalize("customerEmailAddress"), "customer email address")
        self.assertEqual(text.normalize("Cust. E-Mail"), "cust e mail")
        self.assertEqual(text.normalize("HTTPStatusCode"), "http status code")
        self.assertEqual(text.normalize("EMAIL_2"), "email 2")

    def test_tokenize_drops_stopwords(self):
        self.assertEqual(text.tokenize("the customer id"), ["customer", "id"])


class TestSimilarity(unittest.TestCase):
    def test_levenshtein(self):
        self.assertEqual(similarity.levenshtein("kitten", "sitting"), 3)
        self.assertEqual(similarity.levenshtein("abc", "abc"), 0)

    def test_jaro_winkler_prefix_boost(self):
        self.assertGreater(similarity.jaro_winkler("qty", "quantity"),
                           similarity.jaro("qty", "quantity") - 0.001)
        self.assertEqual(similarity.jaro_winkler("email", "email"), 1.0)

    def test_jaccard(self):
        self.assertEqual(similarity.jaccard(["a", "b"], ["a", "b"]), 1.0)
        self.assertEqual(similarity.jaccard(["a"], ["b"]), 0.0)

    def test_monge_elkan_reordered(self):
        s = similarity.symmetric_monge_elkan(["home", "phone"], ["phone", "home"])
        self.assertGreater(s, 0.95)


class TestKnowledge(unittest.TestCase):
    def test_synonym_dob(self):
        self.assertEqual(knowledge.synonym_score("dob", "date of birth"), 1.0)

    def test_synonym_zip_postal(self):
        self.assertEqual(knowledge.synonym_score("zip", "postal code"), 1.0)

    def test_unrelated(self):
        self.assertEqual(knowledge.synonym_score("color", "velocity"), 0.0)

    def test_compound_names_need_attribute_overlap(self):
        # Sharing only an entity concept must not look like a synonym.
        self.assertEqual(
            knowledge.synonym_score("customer email", "user phone"), 0.0
        )
        self.assertEqual(
            knowledge.synonym_score("order date", "purchase amount"), 0.0
        )

    def test_state_means_province_not_status(self):
        self.assertEqual(knowledge.synonym_score("state", "province"), 1.0)
        self.assertEqual(knowledge.synonym_score("state", "status"), 0.0)

    def test_spend_lifetime_value(self):
        self.assertEqual(
            knowledge.synonym_score("spend", "lifetime value"), 1.0
        )

    def test_rebuild_index_picks_up_custom_groups(self):
        knowledge.SYNONYM_GROUPS.append(["widget", "gadget"])
        try:
            self.assertEqual(knowledge.synonym_score("widget", "gadget"), 0.0)
            knowledge.rebuild_index()
            self.assertEqual(knowledge.synonym_score("widget", "gadget"), 1.0)
        finally:
            knowledge.SYNONYM_GROUPS.pop()
            knowledge.rebuild_index()


class TestProfiling(unittest.TestCase):
    def test_email_type(self):
        p = profile_column(["a@x.com", "b@y.org", "c@z.net"])
        self.assertEqual(p.semantic_type, "email")

    def test_integer_range(self):
        p = profile_column(["1", "2", "3", "100"])
        self.assertTrue(p.numeric)
        self.assertEqual(p.num_max, 100.0)

    def test_postal_not_integer(self):
        p = profile_column(["90210", "10001", "60614"])
        self.assertEqual(p.semantic_type, "postal")

    def test_currency_related_to_float(self):
        a = profile_column(["$1,299.50", "$742.00", "$3,050.75"])
        b = profile_column(["850.00", "1620.00", "99.50"])
        self.assertEqual(a.semantic_type, "currency")
        self.assertIn(b.semantic_type, ("float", "integer"))
        self.assertGreater(profile_similarity(a, b), 0.5)

    def test_name_hint_not_substring(self):
        self.assertEqual(type_hint_from_name("candidate"), "unknown")
        self.assertEqual(type_hint_from_name("paramount"), "unknown")
        self.assertEqual(type_hint_from_name("update"), "unknown")
        self.assertEqual(type_hint_from_name("email"), "email")
        self.assertEqual(type_hint_from_name("lifetime_value"), "currency")

    def test_value_overlap_beats_names(self):
        # Columns with totally different names but shared enum values.
        a = profile_column(["ACTIVE", "INACTIVE", "PENDING"] * 5)
        b = profile_column(["ACTIVE", "PENDING", "INACTIVE"] * 5)
        self.assertGreater(profile_similarity(a, b), 0.5)


class TestTransforms(unittest.TestCase):
    def test_iso_date_month_first_default(self):
        t = get_transform("to_iso_date")
        self.assertEqual(t.apply("01/02/2023"), "2023-01-02")
        self.assertEqual(t.apply("12/24/1985"), "1985-12-24")

    def test_iso_date_dayfirst_policy(self):
        t = make_iso_date_transform(dayfirst=True)
        self.assertEqual(t.apply("01/02/2023"), "2023-02-01")

    def test_infer_dayfirst_from_column(self):
        self.assertIs(infer_dayfirst(["01/02/1990", "12/24/1985", "07/09/1978"]), False)
        self.assertIs(infer_dayfirst(["13/02/1990", "07/09/1978"]), True)
        self.assertIsNone(infer_dayfirst(["01/02/1990", "07/09/1978"]))

    def test_bool(self):
        t = get_transform("to_bool")
        self.assertIs(t.apply("YES"), True)
        self.assertIs(t.apply("0"), False)

    def test_currency(self):
        t = get_transform("strip_currency")
        self.assertEqual(t.apply("$1,299.50"), 1299.50)

    def test_name_split_suggested_for_full_name(self):
        sp = profile_column(["John Smith", "Jane Doe"])
        t = suggest_transform("full_name", "first_name", sp, profile_column(["x"]))
        self.assertEqual(t.name, "split_first_name")
        self.assertEqual(t.apply("John Smith"), "John")

    def test_fname_does_not_suggest_split(self):
        sp = profile_column(["John", "Jane"])
        t = suggest_transform("fname", "first_name", sp, profile_column(["x"]))
        self.assertEqual(t.name, "identity")


class TestMapper(unittest.TestCase):
    def test_maps_messy_names(self):
        mapper = SmartFieldMapper()
        plan = mapper.map_schema(
            source_fields=["CustEmail", "fname", "lname", "DOB", "ZipCode"],
            target_fields=["email", "first_name", "last_name", "date_of_birth", "postal_code"],
        )
        d = plan.as_dict()
        self.assertEqual(d["email"], "CustEmail")
        self.assertEqual(d["first_name"], "fname")
        self.assertEqual(d["last_name"], "lname")
        self.assertEqual(d["date_of_birth"], "DOB")
        self.assertEqual(d["postal_code"], "ZipCode")

    def test_one_to_one_no_duplicate_targets(self):
        mapper = SmartFieldMapper()
        plan = mapper.map_schema(
            source_fields=["name", "name2"],
            target_fields=["first_name", "last_name"],
        )
        used = [m.source for m in plan.mappings if m.source]
        self.assertEqual(len(used), len(set(used)))

    def test_value_profiling_disambiguates(self):
        # Two same-named-ish source cols; values decide which is the email.
        mapper = SmartFieldMapper()
        rows = [
            {"a": "john@x.com", "b": "555-123-4567"},
            {"a": "jane@y.com", "b": "555-987-6543"},
        ]
        plan = mapper.map_schema(
            source_fields=["a", "b"],
            target_fields=["email", "phone"],
            source_rows=rows,
        )
        d = plan.as_dict()
        self.assertEqual(d["email"], "a")
        self.assertEqual(d["phone"], "b")

    def test_connect_applies_transform(self):
        mapper = SmartFieldMapper()
        rows = [
            {"full_name": "John Smith", "DOB": "01/02/1990"},
            {"full_name": "Jane Doe", "DOB": "12/24/1985"},
        ]
        plan = mapper.map_schema(
            source_fields=["full_name", "DOB"],
            target_fields=["first_name", "date_of_birth"],
            source_rows=rows,
        )
        out = mapper.connect(plan, rows)
        self.assertEqual(out[0]["first_name"], "John")
        # Column evidence (12/24) forces month-first for the whole field.
        self.assertEqual(out[0]["date_of_birth"], "1990-01-02")
        self.assertEqual(out[1]["date_of_birth"], "1985-12-24")

    def test_demo_maps_spend_to_lifetime_value(self):
        mapper = SmartFieldMapper()
        src_fields = [
            "CustEmail", "fname", "lname", "DOB", "Cell",
            "ZipCode", "SignupDate", "Spend",
        ]
        tgt_fields = [
            "email", "first_name", "last_name", "date_of_birth", "phone",
            "postal_code", "created_at", "lifetime_value",
        ]
        rows = [
            {
                "CustEmail": "John@Acme.com", "fname": "John", "lname": "Smith",
                "DOB": "01/02/1990", "Cell": "555-123-4567", "ZipCode": "90210",
                "SignupDate": "03/15/2023", "Spend": "$1,299.50",
            },
            {
                "CustEmail": "jane@beta.io", "fname": "Jane", "lname": "Doe",
                "DOB": "12/24/1985", "Cell": "555-987-6543", "ZipCode": "10001",
                "SignupDate": "06/01/2023", "Spend": "$742.00",
            },
        ]
        plan = mapper.map_schema(
            src_fields, tgt_fields, source_rows=rows,
            target_rows=[
                {
                    "email": "a@x.com", "first_name": "A", "last_name": "B",
                    "date_of_birth": "1990-01-01", "phone": "1",
                    "postal_code": "94103", "created_at": "2023-01-10",
                    "lifetime_value": "850.00",
                }
            ],
        )
        self.assertEqual(plan.as_dict()["lifetime_value"], "Spend")
        self.assertEqual(plan.coverage, 1.0)
        spend = next(m for m in plan.mappings if m.target == "lifetime_value")
        self.assertEqual(spend.transform.name, "strip_currency")

    def test_alternatives_keep_source_target_polarity(self):
        mapper = SmartFieldMapper()
        plan = mapper.map_schema(
            source_fields=["CustEmail", "Cell"],
            target_fields=["email", "phone"],
        )
        email = next(m for m in plan.mappings if m.target == "email")
        self.assertTrue(email.alternatives)
        for alt in email.alternatives:
            self.assertIn(alt.source, ("CustEmail", "Cell"))
            self.assertEqual(alt.target, "email")

    def test_false_friend_compounds_not_auto_matched(self):
        mapper = SmartFieldMapper()
        plan = mapper.map_schema(
            source_fields=["customer_email", "order_date"],
            target_fields=["user_phone", "purchase_amount"],
        )
        # These must not clear the bar just because they share entity vocab.
        self.assertIsNone(plan.as_dict()["user_phone"])
        self.assertIsNone(plan.as_dict()["purchase_amount"])

    def test_coverage_and_summary(self):
        mapper = SmartFieldMapper()
        plan = mapper.map_schema(["email"], ["email", "totally_unknown_xyz"])
        self.assertLess(plan.coverage, 1.0)
        self.assertIn("coverage", plan.summary())


class TestMemory(unittest.TestCase):
    def test_prior_boosts_confidence(self):
        mem = MappingMemory()
        for _ in range(5):
            mem.confirm("weird_legacy_code", "customer_status")
        self.assertGreater(mem.prior("weird_legacy_code", "customer_status"), 0.9)

        mapper = SmartFieldMapper(memory=mem)
        plan = mapper.map_schema(["weird_legacy_code"], ["customer_status"])
        self.assertEqual(plan.as_dict()["customer_status"], "weird_legacy_code")
        self.assertGreater(plan.mappings[0].confidence, 0.9)

    def test_learn_defaults_to_auto_only(self):
        mem = MappingMemory()
        mapper = SmartFieldMapper(memory=mem)
        plan = mapper.map_schema(
            source_fields=["fname", "CustEmail"],
            target_fields=["first_name", "email"],
        )
        n = mapper.learn(plan)
        auto_targets = {m.target for m in plan.mappings if m.status == "auto" and m.source}
        skipped = {
            m.target for m in plan.mappings
            if m.source and m.status in ("review", "low")
        }
        for t in auto_targets:
            self.assertGreater(mem.prior(plan.as_dict()[t], t), 0.0)
        for t in skipped:
            self.assertEqual(mem.prior(plan.as_dict()[t], t), 0.0)
        self.assertEqual(n, len(auto_targets))
        self.assertTrue(skipped)  # fname should remain unlearned by default

    def test_persistence_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "mem.json")
            mem = MappingMemory(path)
            mem.confirm("src", "tgt")
            mem.save()
            mem2 = MappingMemory(path)
            self.assertGreater(mem2.prior("src", "tgt"), 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
