import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.evaluate_synthetic_parser import evaluate_manifest, load_manifest, main


class SyntheticParserEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "manifest.csv"

    def row(self, identifier="1", group="source1", **changes):
        row = {
            "id": identifier, "file_name": f"{identifier}.jpg",
            "source_group": group, "label_language": "zh",
            "selected_part": "outer", "original_text": "面料\n腈纶 60%\n氨纶 40%",
            "answer_materials": "acrylic;spandex", "answer_ratios": "60;40",
            "normalized_materials": "acrylic;spandex", "normalized_ratios": "60;40",
            "parts_json": json.dumps({"outer": {"acrylic": 60, "spandex": 40}}),
        }
        row.update(changes)
        return row

    def write_rows(self, rows):
        with self.path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def test_grouped_metrics_keep_strict_material_and_part_scores_separate(self):
        self.write_rows([self.row("1"), self.row("2"), self.row("3", "source2", label_language="ja")])
        calls = []

        def label(text):
            calls.append(text)
            return {"materials": {"acrylic": 60, "spandex": 40}, "selected_part": "lining"}

        report = evaluate_manifest(self.path, label, lambda _: {"acrylic": 60, "polyurethane": 40})
        self.assertEqual(len(calls), 2)
        self.assertEqual(report["summary"]["image_rows"], 3)
        self.assertEqual(report["summary"]["unique_source_groups"], 2)
        metrics = report["metrics"]
        self.assertEqual(metrics["image_rows"]["parse_label_materials_exact"]["passed"], 3)
        self.assertEqual(metrics["unique_source_groups"]["parse_label_materials_exact"]["passed"], 2)
        self.assertEqual(metrics["image_rows"]["parse_materials_exact"]["passed"], 0)
        self.assertEqual(metrics["image_rows"]["selected_part_exact"]["passed"], 0)
        self.assertEqual(report["per_language"]["zh"]["image_rows"]["total"], 2)
        self.assertEqual(len(report["source_failures"]), 2)
        self.assertEqual(report["source_results"][0]["notes"][0]["kind"], "ambiguous_material_label")

    def test_exact_comparison_does_not_apply_ratio_tolerance(self):
        self.write_rows([self.row()])
        predicted = {"acrylic": 60.00001, "spandex": 39.99999}
        report = evaluate_manifest(self.path, lambda _: {"materials": predicted, "selected_part": "outer"}, lambda _: predicted)
        self.assertEqual(report["metrics"]["image_rows"]["parse_materials_exact"]["passed"], 0)

    def test_policy_metadata_is_recorded_without_remapping_expected_answers(self):
        row = self.row(
            material_label_policy="kdpp-fiber-labels-v1",
            source_parts_json=json.dumps({"outer": {"acrylic": 60, "spandex": 40}}),
            answer_materials="acrylic;polyurethane", normalized_materials="acrylic;polyurethane",
            parts_json=json.dumps({"outer": {"acrylic": 60, "polyurethane": 40}}),
        )
        self.write_rows([row])
        predicted = {"acrylic": 60, "spandex": 40}
        report = evaluate_manifest(self.path, lambda _: {"materials": predicted, "selected_part": "outer"}, lambda _: predicted)
        self.assertEqual(report["metrics"]["image_rows"]["parse_materials_exact"]["passed"], 0)
        self.assertEqual(report["source_results"][0]["source_parts"]["outer"]["spandex"], 40)

        predicted = {"acrylic": 60, "polyurethane": 40}
        report = evaluate_manifest(self.path, lambda _: {"materials": predicted, "selected_part": "outer"}, lambda _: predicted)
        self.assertEqual(report["metrics"]["image_rows"]["parse_materials_exact"]["passed"], 1)
        self.assertEqual(report["label_issue_sources"], [])
        self.assertEqual(report["source_results"][0]["notes"][0]["kind"], "material_key_convention")

    def test_incomplete_or_inconsistent_source_provenance_is_rejected(self):
        cases = [
            {"material_label_policy": "kdpp-fiber-labels-v1"},
            {"source_parts_json": self.row()["parts_json"]},
            {"material_label_policy": "kdpp-fiber-labels-v1", "source_parts_json": "[]"},
            {"material_label_policy": "kdpp-fiber-labels-v1", "source_parts_json": '{"lining":{"cotton":100}}'},
            {"material_label_policy": "kdpp-fiber-labels-v1", "source_parts_json": '{"outer":{"cotton":90}}'},
            {"material_label_policy": "kdpp-fiber-labels-v1", "source_parts_json": '{"outer":{"cotton":100}}'},
            {"material_label_policy": "unknown", "source_parts_json": self.row()["parts_json"]},
        ]
        for changes in cases:
            with self.subTest(changes=changes):
                self.write_rows([self.row(**changes)])
                with self.assertRaises(ValueError):
                    load_manifest(self.path)
        first = self.row("1", material_label_policy="kdpp-fiber-labels-v1",
                         source_parts_json=self.row()["parts_json"],
                         answer_materials="acrylic;polyurethane", normalized_materials="acrylic;polyurethane",
                         parts_json='{"outer":{"acrylic":60,"polyurethane":40}}')
        second = dict(first, id="2", file_name="2.jpg", source_parts_json='{"outer":{"acrylic":60,"polyurethane":40}}')
        self.write_rows([first, second])
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            load_manifest(self.path)

    def test_inconsistent_source_group_is_rejected_before_parsing(self):
        self.write_rows([self.row("1"), self.row("2", original_text="different source text")])
        def forbidden(_):
            self.fail("A malformed manifest must be rejected before parser calls")
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            evaluate_manifest(self.path, forbidden, forbidden)

    def test_malformed_answers_are_rejected(self):
        cases = [
            {"answer_ratios": "60;30"},
            {"answer_ratios": "60"},
            {"answer_ratios": "NaN;40"},
            {"answer_materials": "acrylic;acrylic"},
            {"normalized_ratios": "61;39"},
            {"selected_part": "lining"},
            {"parts_json": '{"outer":{"acrylic":60,"acrylic":60,"spandex":40}}'},
        ]
        for changes in cases:
            with self.subTest(changes=changes):
                self.write_rows([self.row(**changes)])
                with self.assertRaises(ValueError):
                    load_manifest(self.path)

    def test_missing_field_and_empty_manifest_are_rejected(self):
        row = self.row()
        del row["original_text"]
        self.write_rows([row])
        with self.assertRaisesRegex(ValueError, "missing fields"):
            load_manifest(self.path)
        self.write_rows([self.row()])
        header = self.path.read_text(encoding="utf-8-sig").splitlines()[0]
        self.path.write_text(header + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "no data rows"):
            load_manifest(self.path)

    def test_parser_exception_is_recorded_as_failure(self):
        self.write_rows([self.row()])
        def broken(_):
            raise RuntimeError("parser failed")
        report = evaluate_manifest(self.path, broken, broken)
        failure = report["source_failures"][0]
        self.assertEqual(failure["parse_label"]["error"], "RuntimeError: parser failed")
        self.assertEqual(report["metrics"]["image_rows"]["parse_label_materials_exact"]["passed"], 0)


if __name__ == "__main__":
    unittest.main()
