import unittest

from apps.text.ocr_text import build_candidate, choose_best_candidate
from apps.text.parse_label import parse_label, parse_materials


class ParseMaterialsRegressionTest(unittest.TestCase):
    def test_recovers_missing_leading_digit_in_low_total_group(self):
        text = "\ud63c\uc6a9\ub960 \ud3f4\ub9ac\uc5d0\uc2a4\ud1302%, \ud3f4\ub9ac\uc6b0\ub808\ud0c4 6% 1"

        self.assertEqual(
            parse_materials(text),
            {"polyester": 94, "polyurethane": 6},
        )

    def test_ignores_stray_number_between_material_and_ratio(self):
        text = "\u54c1\u8cea\u7dbf 36 50% \u30a2\u30af\u30ea\u30eb 50%"

        self.assertEqual(
            parse_materials(text),
            {"cotton": 50, "acrylic": 50},
        )

    def test_repairs_ocr_number_overread_for_single_material(self):
        text = "COTTON 2000 RECOMMEND DRY CLEAN"

        self.assertEqual(parse_materials(text), {"cotton": 100})

    def test_pairs_material_list_with_ratio_list(self):
        text = "\uac89\uac10 \uba74(Cotton) \ud3f4\ub9ac\uc5d0\uc2a4\ud130(Polyester) \uc81c\uc678 70% 30%"

        self.assertEqual(
            parse_materials(text),
            {"cotton": 70, "polyester": 30},
        )

    def test_repairs_split_korean_spandex_token(self):
        text = "\uac89\uac10 \uba74 74% \ud3f4\ub9ac\uc5d0\uc2a4\ud130 19% \uc2a4 \ud310 \u30fb7%"

        self.assertEqual(
            parse_materials(text),
            {"cotton": 74, "polyester": 19, "spandex": 7},
        )

    def test_prefers_clear_single_composition_over_later_noise(self):
        text = "cotton 100 care text cotton 95 polyurethane 5"

        self.assertEqual(parse_materials(text), {"cotton": 100})

    def test_parse_label_success_shape(self):
        result = parse_label("\uba74 100%")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["materials"], {"cotton": 100})
        self.assertEqual(result["materials_korean"], "\uba74 100%")


class OcrCandidateSelectionRegressionTest(unittest.TestCase):
    def test_original_candidate_wins_when_preprocessed_finds_conflicting_materials(self):
        original = build_candidate("original", "cotton 100")
        preprocessed = build_candidate("preprocessed", "cotton 95 polyurethane 5")

        selected = choose_best_candidate([original, preprocessed])

        self.assertEqual(selected.source, "original")
        self.assertEqual(selected.materials, {"cotton": 100})


if __name__ == "__main__":
    unittest.main()
