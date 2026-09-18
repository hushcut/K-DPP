import copy
import csv
import json
import random
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import ImageDraw


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from apps.synthetic import label_generator as generator
from apps.text.parse_label import parse_materials


POLICY = "kdpp-fiber-labels-v2"
SOURCE_COMPOSITION = {"cotton": 80, "spandex": 5, "polyurethane": 15}
EXPECTED_COMPOSITIONS = {
    "en": {"cotton": 80, "spandex": 5, "polyurethane": 15},
    "ko": {"cotton": 80, "spandex": 5, "polyurethane": 15},
    "ja": {"cotton": 80, "spandex": 5, "polyurethane": 15},
    "zh": {"cotton": 80, "spandex": 5, "polyurethane": 15},
}
# Fixed expectations make a change in the generator and parser contract visible.
# They must not be constructed from the generator's own material-name table.
EXPECTED_LINES = {
    "en": ["COTTON  80%", "SPANDEX  5%", "POLYURETHANE  15%"],
    "ko": ["면  80%", "스판덱스  5%", "폴리우레탄  15%"],
    "ja": ["綿  80%", "スパンデックス  5%", "ポリウレタン  15%"],
    "zh": ["棉  80%", "氨纶  5%", "聚氨酯  15%"],
}


def make_config(output_dir: Path) -> dict:
    return {
        "dataset_name": "material_policy_test",
        "generator_version": "test",
        "seed": 1234,
        "base_label_count": 1,
        "variants_per_label": 2,
        "image_width": 800,
        "image_height": 640,
        "languages": ["en"],
        "layouts": ["material_first"],
        "conditions": ["clean"],
        "themes": ["white"],
        "part_label_probability": 0,
        "materials": ["cotton", "spandex", "polyurethane"],
        "jpeg_quality_min": 90,
        "jpeg_quality_max": 90,
        "contact_sheet_limit": 2,
        "output_dir": str(output_dir),
    }


class SyntheticMaterialPolicyTests(unittest.TestCase):
    def test_chinese_policy_keeps_elastic_material_keys_distinct(self) -> None:
        source = {
            "outer": {"cotton": 80, "spandex": 5, "polyurethane": 15},
            "lining": {"nylon": 90, "spandex": 10},
            "rib": {"cotton": 95, "polyurethane": 5},
        }
        before = copy.deepcopy(source)

        actual = generator.normalize_label_parts(source, "zh")

        self.assertEqual(actual, source)
        self.assertEqual(source, before)
        for part in source:
            self.assertEqual(sum(actual[part].values()), 100)
            self.assertIsNot(actual[part], source[part])
        actual["rib"]["cotton"] = 0
        self.assertEqual(source, before)

    def test_all_languages_return_independent_part_dictionaries(self) -> None:
        source = {"generic": copy.deepcopy(SOURCE_COMPOSITION)}
        for language in ("en", "ko", "ja", "zh"):
            with self.subTest(language=language):
                actual = generator.normalize_label_parts(source, language)
                self.assertEqual(actual, {
                    "generic": {"cotton": 80, "spandex": 5, "polyurethane": 15},
                })
                self.assertIsNot(actual, source)
                self.assertIsNot(actual["generic"], source["generic"])
                actual["generic"]["spandex"] = 0
                self.assertEqual(source["generic"], SOURCE_COMPOSITION)

    def test_four_language_parser_results_follow_fixed_label_contract(self) -> None:
        for language, lines in EXPECTED_LINES.items():
            with self.subTest(language=language):
                self.assertEqual(
                    parse_materials("\n".join(lines)),
                    EXPECTED_COMPOSITIONS[language],
                )
        # Chinese text elsewhere in a label must not make explicit English
        # SPANDEX and POLYURETHANE indistinguishable to the parser.
        self.assertEqual(
            parse_materials("纤维成分\nSPANDEX 5%\nPOLYURETHANE 15%\nCOTTON 80%"),
            {"spandex": 5, "polyurethane": 15, "cotton": 80},
        )

    def test_spec_retains_raw_composition_under_v2_policy(self) -> None:
        raw = copy.deepcopy(SOURCE_COMPOSITION)
        config = make_config(Path("unused_policy_test_output"))
        config["languages"] = ["zh"]
        with patch.object(generator, "_choose_composition", return_value=raw):
            spec = generator._make_spec(0, config, random.Random(config["seed"]))

        self.assertEqual(spec.source_parts, {"generic": SOURCE_COMPOSITION})
        self.assertEqual(spec.parts, {"generic": SOURCE_COMPOSITION})
        self.assertEqual(spec.answer, SOURCE_COMPOSITION)
        self.assertEqual(raw, SOURCE_COMPOSITION)
        self.assertIsNot(spec.parts["generic"], spec.source_parts["generic"])

    def test_rendered_text_manifest_and_source_lineage_agree_for_four_languages(self) -> None:
        original_draw_text = ImageDraw.ImageDraw.text
        with tempfile.TemporaryDirectory() as temp:
            for language in ("en", "ko", "ja", "zh"):
                with self.subTest(language=language):
                    output = Path(temp) / language
                    config = make_config(output)
                    config["languages"] = [language]
                    # Omission exercises the default contract, including its
                    # presence in the manifest for every generated variant.
                    raw = copy.deepcopy(SOURCE_COMPOSITION)
                    drawn_text = []

                    def record_text(draw, xy, text, *args, **kwargs):
                        drawn_text.append(text)
                        return original_draw_text(draw, xy, text, *args, **kwargs)

                    with (
                        patch.object(generator, "_choose_composition", return_value=raw),
                        patch.object(ImageDraw.ImageDraw, "text", new=record_text),
                    ):
                        generator.generate_dataset(config)

                    with (output / "manifest.csv").open(
                        "r", encoding="utf-8-sig", newline=""
                    ) as stream:
                        rows = list(csv.DictReader(stream))

                    self.assertEqual(len(rows), 2)
                    self.assertEqual(raw, SOURCE_COMPOSITION)
                    for line in EXPECTED_LINES[language]:
                        self.assertEqual(drawn_text.count(line), 2)
                    for row in rows:
                        self.assertEqual(row["material_label_policy"], POLICY)
                        self.assertEqual(json.loads(row["source_parts_json"]), {
                            "generic": SOURCE_COMPOSITION,
                        })
                        self.assertEqual(json.loads(row["parts_json"]), {
                            "generic": EXPECTED_COMPOSITIONS[language],
                        })
                        answer = dict(zip(
                            row["answer_materials"].split(";"),
                            map(int, row["answer_ratios"].split(";")),
                        ))
                        self.assertEqual(answer, EXPECTED_COMPOSITIONS[language])
                        self.assertEqual(row["normalized_materials"], row["answer_materials"])
                        self.assertEqual(row["normalized_ratios"], row["answer_ratios"])
                        for line in EXPECTED_LINES[language]:
                            self.assertIn(line, row["original_text"].splitlines())
                        if language == "zh":
                            self.assertEqual(row["original_text"].count("氨纶"), 1)
                            self.assertEqual(row["original_text"].count("聚氨酯"), 1)
                            self.assertNotIn("SPANDEX", row["original_text"])
                        self.assertEqual(parse_materials(row["original_text"]), answer)
                        self.assertTrue((output / "images" / row["file_name"]).is_file())

    def test_explicit_supported_policy_is_accepted_and_unknown_policy_is_rejected(self) -> None:
        self.assertEqual(generator.MATERIAL_LABEL_POLICY, POLICY)
        with tempfile.TemporaryDirectory() as temp:
            config = make_config(Path(temp) / "dataset")
            config["material_label_policy"] = POLICY
            generator._validate_config(config)
            config["material_label_policy"] = "unknown-material-policy"
            with self.assertRaises(ValueError):
                generator.generate_dataset(config)


if __name__ == "__main__":
    unittest.main()
