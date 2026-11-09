"""실사진 라벨의 겉감 표기·제외 문구·연락처 번호를 조성 근거와 구분하는 회귀 검사."""

from io import BytesIO

from PIL import Image
import pytest

from apps.service.label_analysis import analyze_ocr_result
from apps.text import ocr_text
from apps.text.parse_label import parse_label


def run_with_payloads(monkeypatch, payloads):
    responses = iter(payloads)
    calls = []
    monkeypatch.setattr(ocr_text, "_get_vision_client", lambda *_args: object())
    monkeypatch.setattr(ocr_text, "preprocess_image_bytes", lambda _content: b"preprocessed")

    def fake_ocr(_client, content, **_kwargs):
        calls.append(content)
        return next(responses)

    monkeypatch.setattr(ocr_text, "_run_google_ocr", fake_ocr)
    buffer = BytesIO()
    Image.new("RGB", (80, 80), "white").save(buffer, format="PNG")
    result = ocr_text.run_ocr_bytes(
        buffer.getvalue(), enable_reflection=False, enable_denoised=False, enable_rotated=False,
    )
    return analyze_ocr_result(result), calls


@pytest.mark.parametrize("text", [
    "쉘: 100% 면/장식 제외",
    "シェル: 100% 綿/コットン/装飾部分を除く",
    "몸체: 100% 면",
    "面料:100%棉/不包括裝飾部分",
    "kain luar: 100% katun/ hiasan",
])
def test_written_shell_headings_and_exclusions_keep_outer_composition(text):
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["materials"] == {"cotton": 100}
    assert result["selected_part"] == "outer"


@pytest.mark.parametrize(("text", "part"), [
    ("안감\n소프트쉘 재킷\n면 95%\n스판덱스 5%", "lining"),
    ("주머니감\n미쉘\n면 100%", "pocket"),
    ("소프트쉘 자켓\n폴리에스터 92%\n스판덱스 8%", "generic"),
    ("면 100%\n(주)미쉘코리아", "generic"),
    ("ソフトシェル ジャケット\n綿 100%", "generic"),
])
def test_shell_alias_inside_a_longer_word_does_not_name_the_outer_part(text, part):
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["selected_part"] == part


def test_product_name_with_shell_alias_cannot_separate_a_second_composition():
    assert parse_label("안감\n폴리에스터 100%\n소프트쉘 자켓\n면 100%")["status"] == "failed"


@pytest.mark.parametrize("code", [
    "2-9639/080-023-9639", "+82.1600.4775.", "341-479786(53-02)", "485-37 212945",
    "80~120", "80-120",
])
@pytest.mark.parametrize("placement", ["before", "after"])
def test_separated_contact_codes_and_size_ranges_do_not_reject_composition(code, placement):
    text = f"{code}\nCOTTON 100%" if placement == "before" else f"COTTON 100%\n{code}"
    result = parse_label(text)
    assert result["status"] == "success", result
    assert result["materials"] == {"cotton": 100}


@pytest.mark.parametrize("ratios", ["40~60", "30-70", "40 - 60", "(60-40)"])
def test_separated_ratio_shaped_rows_remain_composition_evidence(ratios):
    result = parse_label(f"COTTON 100%\n{ratios}")
    assert result["status"] == "failed", result
    assert result["materials"] == {}



@pytest.mark.parametrize("number_row", ["100.0000001/5", "100.5-0.5", "99.9-0.2"])
def test_decimal_ratio_rows_are_not_contact_numbers(number_row):
    result = parse_label(f"COTTON 100%\n{number_row}")
    assert result["status"] == "failed", result
    assert result["materials"] == {}


def test_shell_label_contact_row_still_succeeds_through_ocr_metadata(monkeypatch):
    analysis, _calls = run_with_payloads(monkeypatch, [
        "쉘: 100% 면/장식 제외\n+82.1600.4775.", "SIZE M", "SIZE M",
    ])
    assert analysis["status"] == "success", analysis
    assert analysis["materials"] == {"cotton": 100}
    assert analysis["selected_part"] == "outer"
