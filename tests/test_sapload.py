"""Tests for sapload: template introspection, validation, and the pipeline."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from examples.make_sap_template import write_extract, write_template  # noqa: E402
from sapload import Workbook, load, read_template, validate  # noqa: E402
from sapload.xlsx import col_to_index, index_to_col  # noqa: E402


class TestColumnRefs(unittest.TestCase):
    def test_round_trip(self):
        for i in (0, 1, 25, 26, 51, 52, 701, 702):
            self.assertEqual(col_to_index(index_to_col(i)), i)

    def test_known_values(self):
        self.assertEqual(col_to_index("A1"), 0)
        self.assertEqual(col_to_index("Z"), 25)
        self.assertEqual(col_to_index("AA10"), 26)
        self.assertEqual(index_to_col(27), "AB")


class TemplateFixture(unittest.TestCase):
    """Shared fixture: a generated SAP-style template and matching extract."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="sapload-test-")
        cls.template = os.path.join(cls.tmp, "Supplier Invoice_EN.xlsx")
        cls.source = os.path.join(cls.tmp, "claims.csv")
        write_template(cls.template)
        write_extract(cls.source, rows=40)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)


class TestTemplateIntrospection(TemplateFixture):
    def setUp(self):
        self.schema, self.wb, self.sheet = read_template(self.template)

    def test_picks_the_data_sheet_not_the_field_list(self):
        self.assertEqual(self.schema.sheet_name, "Supplier Invoice")

    def test_finds_the_header_rows_unaided(self):
        self.assertEqual(self.schema.label_row, 1)
        self.assertEqual(self.schema.marker_row, 2)
        self.assertEqual(self.schema.technical_row, 3)
        self.assertEqual(self.schema.header_rows, 5)

    def test_prefers_the_technical_name(self):
        self.assertIn("GLAccount", self.schema.names)
        self.assertNotIn("G/L Account", self.schema.names)

    def test_reads_mandatory_and_key_markers(self):
        company = self.schema.by_name("CompanyCode")
        self.assertTrue(company.key)
        self.assertTrue(company.required)
        self.assertTrue(self.schema.by_name("GLAccount").mandatory)
        self.assertFalse(self.schema.by_name("CostCenter").required)

    def test_harvests_value_help_from_dropdowns(self):
        self.assertEqual(self.schema.by_name("DocumentCurrency").allowed,
                         ["AUD", "NZD", "USD"])
        self.assertIsNone(self.schema.by_name("Supplier").allowed)

    def test_reads_field_lengths(self):
        self.assertEqual(self.schema.by_name("DocumentCurrency").max_length, 3)
        self.assertEqual(self.schema.by_name("DocumentHeaderText").max_length, 25)

    def test_infers_types(self):
        self.assertEqual(self.schema.by_name("InvoiceGrossAmount").dtype, "number")
        self.assertEqual(self.schema.by_name("PostingDate").dtype, "date")
        self.assertEqual(self.schema.by_name("Supplier").dtype, "text")

    def test_records_where_each_fact_came_from(self):
        field = self.schema.by_name("DocumentCurrency")
        self.assertIn("technical name row", field.source_of_truth)
        self.assertIn("template dropdown", field.source_of_truth)


class TestValidation(TemplateFixture):
    def setUp(self):
        self.schema, _wb, _sheet = read_template(self.template)

    def _one(self, **overrides):
        row = {
            "CompanyCode": "1000", "SupplierInvoiceIDByInvcgParty": "RCTI-1",
            "Supplier": "700001", "DocumentDate": "2026-08-01",
            "PostingDate": "2026-09-01", "InvoiceGrossAmount": "100.00",
            "DocumentCurrency": "AUD", "GLAccount": "6000010",
        }
        row.update(overrides)
        return row

    def test_clean_row_passes(self):
        self.assertTrue(validate(self.schema, [self._one()]).ok)

    def test_missing_mandatory_is_an_error(self):
        report = validate(self.schema, [self._one(GLAccount="")])
        self.assertFalse(report.ok)
        self.assertIn("required", report.errors[0].message)

    def test_value_outside_the_dropdown_is_an_error(self):
        report = validate(self.schema, [self._one(DocumentCurrency="AU$")])
        self.assertFalse(report.ok)
        self.assertIn("allowed values", report.errors[0].message)

    def test_over_length_is_an_error(self):
        report = validate(self.schema, [self._one(DocumentHeaderText="x" * 40)])
        self.assertFalse(report.ok)
        self.assertIn("longer than", report.errors[0].message)

    def test_non_numeric_amount_is_an_error(self):
        report = validate(self.schema, [self._one(InvoiceGrossAmount="1,240.00 AUD")])
        self.assertFalse(report.ok)
        self.assertIn("number", report.errors[0].message)

    def test_optional_empty_field_is_fine(self):
        self.assertTrue(validate(self.schema, [self._one(CostCenter="")]).ok)

    def test_top_groups_repeated_problems(self):
        rows = [self._one(DocumentCurrency="AU$") for _ in range(5)]
        lines = validate(self.schema, rows).top()
        self.assertTrue(lines[0].startswith("[   5x]"))


class TestPipeline(TemplateFixture):
    def test_maps_every_field_given_one_override(self):
        result = load(self.source, self.template,
                      overrides={"DocumentHeaderText": "descr"})
        self.assertEqual(result.plan.coverage, 1.0)
        by_target = {m.target: m.source for m in result.plan.mappings}
        self.assertEqual(by_target["GLAccount"], "gl_acct")
        self.assertEqual(by_target["Supplier"], "vendor_id")
        self.assertEqual(by_target["AssignmentReference"], "wo_number")
        self.assertEqual(by_target["SupplierInvoiceIDByInvcgParty"], "claim_number")

    def test_ignores_source_system_surrogate_keys(self):
        result = load(self.source, self.template)
        self.assertIn("sys_id", result.plan.unmatched_sources)

    def test_catches_exactly_the_planted_defects(self):
        result = load(self.source, self.template,
                      overrides={"DocumentHeaderText": "descr"})
        self.assertEqual(len(result.validation.bad_rows), 5)

    def test_control_totals_cover_the_amount_column(self):
        result = load(self.source, self.template)
        fields = [t.field for t in result.recon.totals]
        self.assertIn("InvoiceGrossAmount", fields)

    def test_writes_a_file_that_keeps_sap_formatting(self):
        out = os.path.join(self.tmp, "upload.xlsx")
        result = load(self.source, self.template, output_path=out,
                      overrides={"DocumentHeaderText": "descr"})
        self.assertEqual(result.rows_written, 40)

        original = set(zipfile.ZipFile(self.template).namelist())
        self.assertEqual(set(zipfile.ZipFile(out).namelist()), original)

        wb = Workbook(out)
        sheet = wb.sheet("Supplier Invoice")
        self.assertEqual(len(sheet.rows), 45)                    # 5 header + 40
        self.assertEqual(sheet.cell(3, 0), "CompanyCode")        # header intact
        self.assertEqual(sheet.cell(5, 0), "1000")               # data begins
        self.assertEqual(len(sheet.validations), 3)              # dropdowns kept

    def test_only_clean_holds_bad_rows_back(self):
        out = os.path.join(self.tmp, "clean.xlsx")
        result = load(self.source, self.template, output_path=out,
                      only_clean=True, overrides={"DocumentHeaderText": "descr"})
        self.assertEqual(result.rows_written, 35)

    def test_rejects_an_override_naming_an_unknown_column(self):
        with self.assertRaises(ValueError):
            load(self.source, self.template, overrides={"GLAccount": "nope"})

    def test_a_filled_file_still_reads_as_a_template(self):
        out = os.path.join(self.tmp, "again.xlsx")
        load(self.source, self.template, output_path=out)
        schema, _wb, _sheet = read_template(out)
        self.assertEqual(schema.header_rows, 5)
        self.assertEqual(len(schema.fields), 12)


class TestLearningGate(TemplateFixture):
    """Memory must not entrench a guess nobody reviewed."""

    def test_low_confidence_matches_are_not_remembered(self):
        mem = os.path.join(self.tmp, "gate.json")
        load(self.source, self.template, memory_path=mem)
        with open(mem, encoding="utf-8") as fh:
            body = fh.read()
        # vendor_id -> Supplier scores in the review band, so it must not stick.
        self.assertNotIn("vendor id", body)

    def test_reviewer_overrides_are_always_remembered(self):
        mem = os.path.join(self.tmp, "override.json")
        load(self.source, self.template, memory_path=mem,
             overrides={"DocumentHeaderText": "descr"})
        with open(mem, encoding="utf-8") as fh:
            self.assertIn("descr", fh.read())


if __name__ == "__main__":
    unittest.main(verbosity=2)
