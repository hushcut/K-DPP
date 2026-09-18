"""Public parser contracts for supported, complete material percentages."""

import sys
import unittest
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from apps.text.parse_label import parse_label, parse_materials


class MaterialEvidenceTests(unittest.TestCase):
    def test_multiple_percentages_in_one_numeric_column_remain_supported(self) -> None:
        for text in [
            "COTTON POLYESTER 60% 40%",
            "COTTON\nPOLYESTER\n60% 40%",
            "60% 40%\nCOTTON\nPOLYESTER",
            "COTTON\nPOLYESTER\n60 40",
        ]:
            with self.subTest(text=text):
                self.assert_composition(text, {"cotton": 60, "polyester": 40}, "면 60%, 폴리에스터 40%")

    def test_separate_metadata_is_ignored_but_cannot_supply_missing_ratios(self) -> None:
        for metadata in ["TEL: 02-1234-5678", "AB12345", "SIZE 100"]:
            with self.subTest(metadata=metadata):
                self.assert_composition("COTTON 100%\n" + metadata, {"cotton": 100}, "면 100%")
                self.assert_rejected("COTTON\n" + metadata + "\n100")

    def assert_rejected(self, text: str) -> None:
        parsed = parse_label(text)
        self.assertEqual(parsed["status"], "failed", parsed)
        self.assertEqual(parsed["materials"], {})
        self.assertEqual(parsed["materials_korean"], "")
        self.assertEqual(parse_materials(text), {})

    def assert_composition(
        self, text: str, expected: dict, korean: str, part: str = "generic"
    ) -> dict:
        parsed = parse_label(text)
        self.assertEqual(parsed["status"], "success", parsed)
        self.assertEqual(parsed["materials"], expected)
        self.assertEqual(parsed["materials_korean"], korean)
        self.assertEqual(parsed["selected_part"], part)
        self.assertEqual(parse_materials(text), expected)
        return parsed

    def test_missing_materials_and_ratios_are_not_inferred(self) -> None:
        cases = [
            "RAYON 60% UNKNOWN 40%",
            "레이온 60% 알 수 없는 소재 40%",
            "섬유 혼용률 100%",
            "COTTON SIZE 100",
            "COTTON 95% POLYESTER",
            "ONLY COTTON",
            "80% POLYESTER 20%",
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assert_rejected(text)

    def test_totals_are_not_rescaled_to_one_hundred(self) -> None:
        cases = [
            "COTTON 80% POLYESTER 80%",
            "COTTON 60% POLYESTER 39%",
            "COTTON 61% POLYESTER 40%",
            "COTTON 99%",
            "COTTON 101%",
            "COTTON 99.5%",
            "COTTON 92.5% SPANDEX 7.4%",
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assert_rejected(text)

    def test_invalid_numbers_are_not_read_as_valid_fragments(self) -> None:
        cases = [
            "COTTON -100%",
            "COTTON -60% POLYESTER 40%",
            "COTTON 101% POLYESTER -1%",
            "COTTON 1000%",
            "COTTON 1000% POLYESTER 100%",
            "COTTON 92..5% SPANDEX 7.5%",
            "COTTON 92.5.0% SPANDEX 7.5%",
            "COTTON 100.%",
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assert_rejected(text)

    def test_decimal_percentages_are_preserved(self) -> None:
        cases = [
            (
                "COTTON 92.5% SPANDEX 7.5%",
                {"cotton": 92.5, "spandex": 7.5},
                "면 92.5%, 스판덱스 7.5%",
            ),
            (
                "COTTON 99.5% SPANDEX 0.5%",
                {"cotton": 99.5, "spandex": 0.5},
                "면 99.5%, 스판덱스 0.5%",
            ),
            (
                "COTTON 33.33% POLYESTER 33.33% NYLON 33.34%",
                {"cotton": 33.33, "polyester": 33.33, "nylon": 33.34},
                "나일론 33.34%, 면 33.33%, 폴리에스터 33.33%",
            ),
        ]
        for text, expected, korean in cases:
            with self.subTest(text=text):
                self.assert_composition(text, expected, korean)

    def test_multilingual_decimal_percentages(self) -> None:
        cases = [
            "면 92.5% 스판덱스 7.5%",
            "綿92.5% スパンデックス7.5%",
            "ＣＯＴＴＯＮ ９２．５％ ＳＰＡＮＤＥＸ ７．５％",
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assert_composition(
                    text,
                    {"cotton": 92.5, "spandex": 7.5},
                    "면 92.5%, 스판덱스 7.5%",
                )
        self.assert_composition(
            "棉９２．５％ 氨纶７．５％",
            {"cotton": 92.5, "spandex": 7.5},
            "면 92.5%, 스판덱스 7.5%",
        )

    def test_decimal_ratios_before_materials(self) -> None:
        cases = [
            "92.5% COTTON\n7.5% SPANDEX",
            "９２．５％ 綿\n７．５％ スパンデックス",
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assert_composition(
                    text,
                    {"cotton": 92.5, "spandex": 7.5},
                    "면 92.5%, 스판덱스 7.5%",
                )
        self.assert_composition(
            "92.5%面料棉7.5%氨纶\n里料锦纶100%",
            {"cotton": 92.5, "spandex": 7.5},
            "면 92.5%, 스판덱스 7.5%",
            "outer",
        )

    def test_decimal_stacked_columns(self) -> None:
        cases = [
            "COTTON\nSPANDEX\n92.5%\n7.5%",
            "92.5%\n7.5%\nCOTTON\nSPANDEX",
            "綿\nスパンデックス\n９２．５％\n７．５％",
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assert_composition(
                    text,
                    {"cotton": 92.5, "spandex": 7.5},
                    "면 92.5%, 스판덱스 7.5%",
                )

    def test_explicit_complete_integer_compositions_remain_supported(self) -> None:
        cases = [
            ("COTTON 100%", {"cotton": 100}, "면 100%"),
            ("100% COTTON", {"cotton": 100}, "면 100%"),
            (
                "COTTON 60% POLYESTER 40%",
                {"cotton": 60, "polyester": 40},
                "면 60%, 폴리에스터 40%",
            ),
            (
                "COTTON 60 POLYESTER 40",
                {"cotton": 60, "polyester": 40},
                "면 60%, 폴리에스터 40%",
            ),
        ]
        for text, expected, korean in cases:
            with self.subTest(text=text):
                self.assert_composition(text, expected, korean)

    def test_incomplete_outer_is_not_replaced_with_complete_lining(self) -> None:
        cases = [
            "겉감: 레이온 60% 알 수 없는 소재 40%\n안감: 폴리에스터 100%",
            "OUTER: COTTON 95% POLYESTER\nLINING: NYLON 100%",
            "表地：綿95%\n裏地：ナイロン100%",
            "里料：锦纶100%\n面料：棉80% 聚酯纤维80%",
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assert_rejected(text)

    def test_complete_outer_is_selected_with_separate_lining(self) -> None:
        parsed = self.assert_composition(
            "안감: 나일론 100%\n겉감: 면 92.5% 스판덱스 7.5%",
            {"cotton": 92.5, "spandex": 7.5},
            "면 92.5%, 스판덱스 7.5%",
            "outer",
        )
        self.assertEqual(parsed["parts"]["lining"], {"nylon": 100})

    def test_identical_complete_translations_preserve_composition(self) -> None:
        cases = [
            "COTTON 60% POLYESTER 40%\n면 60% 폴리에스터 40%",
            "COTTON 92.5% SPANDEX 7.5%\n綿92.5% スパンデックス7.5%",
        ]
        expected = [
            ({"cotton": 60, "polyester": 40}, "면 60%, 폴리에스터 40%"),
            ({"cotton": 92.5, "spandex": 7.5}, "면 92.5%, 스판덱스 7.5%"),
        ]
        for text, (materials, korean) in zip(cases, expected):
            with self.subTest(text=text):
                self.assert_composition(text, materials, korean)

    def test_conflicting_translations_are_not_averaged_or_overwritten(self) -> None:
        cases = [
            "COTTON 60% POLYESTER 40%\n면 70% 폴리에스터 30%",
            "COTTON 100%\n綿95% スパンデックス5%",
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assert_rejected(text)

    def test_percent_marked_ratios_may_touch_english_material_names(self) -> None:
        cases = [
            ("100%COTTON", {"cotton": 100}, "면 100%"),
            (
                "60%COTTON 40%POLYESTER",
                {"cotton": 60, "polyester": 40},
                "면 60%, 폴리에스터 40%",
            ),
            (
                "COTTON60%POLYESTER40%",
                {"cotton": 60, "polyester": 40},
                "면 60%, 폴리에스터 40%",
            ),
            (
                "92.5%COTTON7.5%SPANDEX",
                {"cotton": 92.5, "spandex": 7.5},
                "면 92.5%, 스판덱스 7.5%",
            ),
        ]
        for text, expected, korean in cases:
            with self.subTest(text=text):
                self.assert_composition(text, expected, korean)

    def test_measurements_are_not_material_percentages(self) -> None:
        cases = [
            "COTTON 100 g",
            "COTTON 100 cm",
            "COTTON 100°C",
            "COTTON 100도",
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assert_rejected(text)

    def test_unicode_signs_and_qualified_ratios_are_not_exact_percentages(self) -> None:
        cases = [
            "COTTON −60% POLYESTER 40%",
            "COTTON –100%",
            "COTTON ±100%",
            "COTTON ≥100%",
            "COTTON ~100%",
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assert_rejected(text)

    def test_duplicate_percent_marks_are_rejected_with_or_without_spaces(self) -> None:
        cases = [
            "COTTON 100%%",
            "COTTON 100 % %",
            "COTTON 60% POLYESTER 40 %  %",
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assert_rejected(text)

    def test_unknown_material_ratios_are_not_shifted_to_known_materials(self) -> None:
        cases = [
            "UNKNOWN 60% COTTON 40% POLYESTER",
            "COTTON 60% UNKNOWN 40% POLYESTER",
            "未知繊維60% 綿40% ポリエステル",
        ]
        for text in cases:
            with self.subTest(text=text):
                self.assert_rejected(text)


if __name__ == "__main__":
    unittest.main()
