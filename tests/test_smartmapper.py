"""Test suite for smartmapper. Run with: python -m pytest  (or python -m unittest)."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smartmapper import SmartFieldMapper, MappingMemory, profile_column  # noqa: E402
from smartmapper import similarity, text, knowledge  # noqa: E402
from smartmapper.transforms import get_transform, suggest_transform  # noqa: E402


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


class TestProfiling(unittest.TestCase):
    def test_email_type(self):
        p = profile_column(["a@x.com", "b@y.org", "c@z.net"])
        self.assertEqual(p.semantic_type, "email")

    def test_integer_range(self):
        p = profile_column(["1", "2", "3", "100"])
        self.assertTrue(p.numeric)
        self.assertEqual(p.num_max, 100.0)

    def test_value_overlap_beats_names(self):
        # Columns with totally different names but shared enum values.
        from smartmapper.profiling import profile_similarity
        a = profile_column(["ACTIVE", "INACTIVE", "PENDING"] * 5)
        b = profile_column(["ACTIVE", "PENDING", "INACTIVE"] * 5)
        self.assertGreater(profile_similarity(a, b), 0.5)


class TestTransforms(unittest.TestCase):
    def test_iso_date(self):
        t = get_transform("to_iso_date")
        self.assertEqual(t.apply("01/02/2023"), "2023-02-01")

    def test_bool(self):
        t = get_transform("to_bool")
        self.assertIs(t.apply("YES"), True)
        self.assertIs(t.apply("0"), False)

    def test_currency(self):
        t = get_transform("strip_currency")
        self.assertEqual(t.apply("$1,299.50"), 1299.50)

    def test_name_split_suggested(self):
        sp = profile_column(["John Smith", "Jane Doe"])
        t = suggest_transform("full_name", "first_name", sp, profile_column(["x"]))
        self.assertEqual(t.apply("John Smith"), "John")


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
        rows = [{"full_name": "John Smith", "DOB": "01/02/1990"}]
        plan = mapper.map_schema(
            source_fields=["full_name", "DOB"],
            target_fields=["first_name", "date_of_birth"],
            source_rows=rows,
        )
        out = mapper.connect(plan, rows)
        self.assertEqual(out[0]["first_name"], "John")
        self.assertEqual(out[0]["date_of_birth"], "1990-02-01")

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
