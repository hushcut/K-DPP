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

    def test_combines_forward_pairs_with_trailing_reverse_pair(self):
        text = "Cotton 51% Polyester 46% 3% Polyurethane"

        self.assertEqual(
            parse_materials(text),
            {"cotton": 51, "polyester": 46, "polyurethane": 3},
        )

    def test_keeps_standard_reverse_pairs(self):
        text = "95% polyester 5% elastane"

        self.assertEqual(
            parse_materials(text),
            {"polyester": 95, "spandex": 5},
        )

    def test_prefers_wool_total_over_cashmere_contained_note(self):
        text = "\uac89\uac10 \ubaa8 100% (\uce90\uc2dc\ubbf8\uc5b4 10%\ud568\uc720) \uc548\uac10 \ud3f4\ub9ac\uc5d0\uc2a4\ud130 100%"

        self.assertEqual(parse_materials(text), {"wool": 100})

    def test_repairs_japanese_cotton_ocr_as_knit_character(self):
        text = "\ubcf8\uccb4 \ub9ac\ube0c\ubd80\ubd84 \u7de8 100%"

        self.assertEqual(parse_materials(text), {"cotton": 100})

    def test_repairs_korean_cotton_ocr_as_man(self):
        text = "\ub9cc 100% 100 \uc911\uc131 \ubd84\ub9ac\uc138\ud0c1"

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
