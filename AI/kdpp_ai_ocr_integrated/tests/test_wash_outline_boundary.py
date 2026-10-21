"""A tub outline can carry temperature digits outside the fiber table."""
import pytest

from apps.text.parse_label import build_line_infos, parse_label
from apps.text import ocr_text
from apps.text.ocr_layout import OcrWord
from apps.service.label_analysis import analyze_ocr_result


@pytest.mark.parametrize('outline', [r'\30', r'\30/', '(300/', '( 400 /', '(600)/'])
@pytest.mark.parametrize('composition', [
    'COTTON 73%\nPOLYESTER 27%',
    '綿 73%\nポリエステル 27%',
    '면 73%\n폴리에스터 27%',
])
def test_outlined_temperature_after_complete_composition_is_metadata(outline, composition):
    result = parse_label(f'{composition}\n{outline}\nMADE IN CHINA')
    assert result['status'] == 'success'
    assert result['materials'] == {'cotton': 73, 'polyester': 27}
    assert result['parse_evidence']['observed_ratios'] == {'generic': [73.0, 27.0]}
    assert build_line_infos(f'{composition}\n{outline}')[-1].is_metadata


@pytest.mark.parametrize('outline', [r'\30', r'\30/', '(300/', '( 400 /', '(600)/'])
@pytest.mark.parametrize('prefix', [
    'COTTON 70%\nPOLYESTER',
    'COTTON 70%',
    'COTTON 100%\nLINING',
    'COTTON 100%\nUNKNOWN FIBER',
    'COTTON 100%\n10%',
])
def test_outline_cannot_complete_or_hide_an_unfinished_declaration(outline, prefix):
    row = build_line_infos(f'{prefix}\n{outline}')[-1]
    assert not row.is_metadata


@pytest.mark.parametrize('number', [
    '30', '40', '(300%', r'\30%', '(300/ 10%', '(300/ COTTON',
    '(300/ UNKNOWN FIBER', '(300/ LINING', '(-300/', '(310/', '(3000/',
])
def test_additional_ratio_and_opaque_suffix_are_not_a_wash_outline(number):
    rows = build_line_infos(f'COTTON 73%\nPOLYESTER 27%\n{number}')
    assert not rows[-1].is_metadata


def test_wash_outline_does_not_hide_a_later_composition_error():
    result = parse_label('COTTON 73%\nPOLYESTER 27%\n(300/\n10%')
    assert result['status'] == 'failed'
    assert result['materials'] == {}


def test_wash_outline_does_not_change_an_explicit_part():
    result = parse_label('SHELL\nCOTTON 73%\nPOLYESTER 27%\n(300/')
    assert result['status'] == 'success'
    assert result['selected_part'] == 'outer'
    assert result['parts'] == {'outer': {'cotton': 73, 'polyester': 27}}


@pytest.mark.parametrize('outline', [r'\30/', '(300/', '( 400 /'])
def test_confirmed_outline_stops_before_extra_ocr_candidates(monkeypatch, outline):
    monkeypatch.setattr(ocr_text, 'validate_image_bytes', lambda *_args, **_kwargs: (
        ocr_text.ValidatedImage(b'original', 'PNG', 100, 100)
    ))
    monkeypatch.setattr(ocr_text, '_resolve_credential_path', lambda *_args: (None, None))
    monkeypatch.setattr(ocr_text, '_get_vision_client', lambda *_args: object())
    monkeypatch.setattr(ocr_text, 'ocr_coordinate_frame', lambda *_args: (
        (1, 0, 0, 0, 1, 0), (0, 0, 100, 100)
    ))
    calls = []

    def provider(_client, content, **_kwargs):
        calls.append(content)
        assert content == b'original'
        text = f'SHELL\nCOTTON 73%\nPOLYESTER 27%\n{outline}'
        words = (
            OcrWord('SHELL', 10, 0, 55, 10),
            OcrWord('COTTON', 10, 20, 55, 30),
            OcrWord('73', 65, 20, 80, 30), OcrWord('%', 82, 20, 90, 30),
            OcrWord('POLYESTER', 10, 40, 60, 50),
            OcrWord('27', 65, 40, 80, 50), OcrWord('%', 82, 40, 90, 50),
            OcrWord(outline, 10, 70, 45, 80),
        )
        return ocr_text.OcrPayload(text, layout_text=text.replace('%', ' %'), layout_words=words)

    def unexpected(*_args, **_kwargs):
        raise AssertionError('A confirmed original must not generate another OCR input')

    monkeypatch.setattr(ocr_text, '_run_google_ocr', provider)
    monkeypatch.setattr(ocr_text, 'preprocess_image_bytes', unexpected)
    result = analyze_ocr_result(ocr_text.run_ocr_bytes(
        b'image', enable_reflection=False, enable_denoised=False,
        enable_rotated=False, enable_material_region=False,
    ))
    assert result['status'] == 'success'
    assert result['materials'] == {'cotton': 73, 'polyester': 27}
    assert result['selected_part'] == 'outer'
    assert result['ocr']['candidate_count'] == 1
    assert calls == [b'original']


@pytest.mark.parametrize('suffix', ['30', '30%', '-30', r'\30%', '(300/ 10%'])
def test_actual_extra_numeric_evidence_still_rejects_the_composition(suffix):
    result = parse_label(f'COTTON 73%\nPOLYESTER 27%\n{suffix}')
    assert result['status'] == 'failed'
    assert result['materials'] == {}
