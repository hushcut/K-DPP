import sys
import unittest
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from apps.text.parse_label import parse_label, parse_materials


class MultilingualMaterialParserTests(unittest.TestCase):
    def assert_composition(self, text: str, expected: dict, part: str = "generic") -> dict:
        parsed = parse_label(text)
        self.assertEqual(parsed["status"], "success")
        self.assertEqual(parsed["materials"], expected)
        self.assertEqual(parsed["selected_part"], part)
        self.assertEqual(parse_materials(text), expected)
        return parsed

    def test_japanese_aliases_in_blends(self) -> None:
        cases = [
            ("綿92% スパンデックス8%", {"cotton": 92, "spandex": 8}),
            ("ビスコース65% ナイロン35%", {"viscose": 65, "nylon": 35}),
            ("カシミヤ60% 羊毛40%", {"cashmere": 60, "wool": 40}),
            ("モダール85% ポリエステル15%", {"modal": 85, "polyester": 15}),
            ("リヨセル72% 綿28%", {"lyocell": 72, "cotton": 28}),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assert_composition(text, expected)

    def test_chinese_aliases_in_blends(self) -> None:
        cases = [
            ("锦纶60% 腈纶40%", {"nylon": 60, "acrylic": 40}),
            ("人造丝65% 聚酯纤维35%", {"rayon": 65, "polyester": 35}),
            ("粘胶纤维85% 棉15%", {"viscose": 85, "cotton": 15}),
            ("蚕丝70% 羊毛30%", {"silk": 70, "wool": 30}),
            ("羊绒60% 羊毛40%", {"cashmere": 60, "wool": 40}),
            ("莫代尔72% 锦纶28%", {"modal": 72, "nylon": 28}),
            ("莱赛尔90% 棉10%", {"lyocell": 90, "cotton": 10}),
            ("腈纶95% 人造丝5%", {"acrylic": 95, "rayon": 5}),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assert_composition(text, expected)

    def test_ratios_before_materials_and_stacked_columns(self) -> None:
        cases = [
            ("65% ビスコース\n35% ナイロン", {"viscose": 65, "nylon": 35}),
            ("莫代尔\n莱赛尔\n锦纶\n55%\n40%\n5%", {"modal": 55, "lyocell": 40, "nylon": 5}),
            ("カシミヤ\n羊毛\n60%\n40%", {"cashmere": 60, "wool": 40}),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assert_composition(text, expected)

    def test_outer_is_selected_even_when_lining_comes_first(self) -> None:
        for text in [
            "裏地\nナイロン100%\n表地\n綿80%\nポリエステル20%",
            "里料\n锦纶100%\n面料\n棉80%\n聚酯纤维20%",
        ]:
            with self.subTest(text=text):
                parsed = self.assert_composition(text, {"cotton": 80, "polyester": 20}, "outer")
                self.assertEqual(parsed["parts"]["lining"], {"nylon": 100})

    def test_adjacent_headers_and_long_material_names(self) -> None:
        cases = [
            ("表地綿80%ポリエステル20%裏地ナイロン100%", {"cotton": 80, "polyester": 20}),
            ("表地スパンデックス100%裏地絹100%", {"spandex": 100}),
            ("里料蚕丝100%面料粘胶纤维80%锦纶20%", {"viscose": 80, "nylon": 20}),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assert_composition(text, expected, "outer")

    def test_rib_is_not_merged_into_outer_or_lining(self) -> None:
        cases = [
            "表地\nカシミヤ60%\n羊毛40%\n裏地\n絹100%\nリブ\n綿95%\nポリウレタン5%",
            "面料\n羊绒60%\n羊毛40%\n里料\n蚕丝100%\n螺纹\n棉95%\n氨纶5%",
        ]
        for text in cases:
            with self.subTest(text=text):
                parsed = self.assert_composition(text, {"cashmere": 60, "wool": 40}, "outer")
                self.assertEqual(parsed["parts"]["lining"], {"silk": 100})
                self.assertEqual(parsed["parts"]["rib"], {"cotton": 95, "polyurethane": 5})

    def test_ratio_before_cjk_header_stays_with_its_part(self) -> None:
        cases = [
            ("95%面料棉5%氨纶\n里料聚酯100%", {"cotton": 95, "polyurethane": 5}),
            ("50%本体綿50%ポリエステル\n裏地ナイロン100%", {"cotton": 50, "polyester": 50}),
            ("80%本体綿20%ポリエステル", {"cotton": 80, "polyester": 20}),
            ("９５％面料棉５％氨纶\n里料蚕丝１００％", {"cotton": 95, "polyurethane": 5}),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assert_composition(text, expected, "outer")

    def test_imitation_or_style_words_do_not_prove_material_content(self) -> None:
        for text in ["面料：仿羊绒100%", "面料：仿蚕丝100%", "表地：カシミヤ風100%", "表地：モダール調100%"]:
            with self.subTest(text=text):
                self.assertEqual(parse_materials(text), {})
                self.assertEqual(parse_label(text)["status"], "failed")

    def test_fullwidth_numbers_and_halfwidth_katakana(self) -> None:
        parsed = self.assert_composition(
            "表地：ﾎﾟﾘｴｽﾃﾙ９５％\nﾎﾟﾘｳﾚﾀﾝ５％\nﾘﾌﾞ：綿１００％",
            {"polyester": 95, "polyurethane": 5},
            "outer",
        )
        self.assertEqual(parsed["parts"]["rib"], {"cotton": 100})
        self.assert_composition("面料：锦纶６０％ 腈纶４０％", {"nylon": 60, "acrylic": 40}, "outer")
        self.assert_composition("ＣＯＴＴＯＮ　８０％ ＰＯＬＹＥＳＴＥＲ　２０％", {"cotton": 80, "polyester": 20})

    def test_existing_korean_english_and_elastic_keys_are_preserved(self) -> None:
        cases = [
            ("면 60% 폴리에스터 40%", {"cotton": 60, "polyester": 40}),
            ("COTTON 95% ELASTANE 5%", {"cotton": 95, "spandex": 5}),
            ("COTTON 95% POLYURETHANE 5%", {"cotton": 95, "polyurethane": 5}),
            ("棉95% 氨纶5%", {"cotton": 95, "polyurethane": 5}),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assert_composition(text, expected)

    def test_unknown_text_and_generator_typo_are_not_material_aliases(self) -> None:
        for text in ["", "未知繊維100%", "腨纶100%"]:
            with self.subTest(text=text):
                self.assertEqual(parse_materials(text), {})
                self.assertEqual(parse_label(text)["status"], "failed")


if __name__ == "__main__":
    unittest.main()
