"""An exact registered heading can retain its part despite OCR word spacing."""
import pytest

from apps.service.label_analysis import analyze_label_text
from apps.text.material_extraction import declared_part, normalize_text
from apps.text.parse_label import parse_label


@pytest.mark.parametrize('heading,part', [
    ('表 地', 'outer'), ('裏 地', 'lining'), ('面 料', 'outer'),
    ('主 面 料', 'outer'), ('外 层', 'outer'), ('外 層', 'outer'),
    ('内 衬', 'lining'), ('內 裡', 'lining'), ('填 充 物', 'filling'),
    ('中 綿', 'filling'), ('口 袋 布', 'pocket'), ('刺 繍', 'embroidery_yarn'),
    ('配 色', 'color_block'), ('袖 部', 'sleeve'), ('羅 紋', 'rib'),
])
@pytest.mark.parametrize('surrounding', ['{}', '[{}]', '{}:'])
def test_standalone_registered_heading_retains_its_part(heading, part, surrounding):
    marker = surrounding.format(heading)
    text = f'{marker}\nCOTTON 73%\nPOLYESTER 27%'
    result = parse_label(text)
    assert declared_part(marker) == part
    assert result['status'] == 'success'
    assert result['selected_part'] == part
    assert result['parts'] == {part: {'cotton': 73, 'polyester': 27}}
    assert result['materials'] == {'cotton': 73, 'polyester': 27}
    expected = parse_label(text.replace(heading, heading.replace(' ', '')))
    assert result['raw_ocr_preview'] == text.replace('\n', ' ')
    assert {key: value for key, value in result.items() if key != 'raw_ocr_preview'} == {
        key: value for key, value in expected.items() if key != 'raw_ocr_preview'
    }


def test_outer_and_lining_rows_stay_in_separate_blocks():
    result = parse_label('表 地\nCOTTON 73%\nPOLYESTER 27%\n裏 地\nNYLON 100%')
    assert result['status'] == 'success'
    assert result['selected_part'] == 'outer'
    assert result['materials'] == {'cotton': 73, 'polyester': 27}
    assert result['parts'] == {'outer': {'cotton': 73, 'polyester': 27}, 'lining': {'nylon': 100}}


def test_an_unread_outer_declaration_cannot_fall_back_to_confirmed_lining():
    result = parse_label('表 地\nUNKNOWN 100%\n裏 地\nPOLYESTER 100%')
    assert result['status'] == 'failed'
    assert result['error_code'] == 'incomplete_part_composition'
    assert result['parts'] == result['materials'] == {}
    assert 'outer' in result['parse_evidence']['rejected_composition_parts']


def test_a_trailing_standalone_heading_keeps_existing_marker_order():
    result = parse_label('COTTON 73%\nPOLYESTER 27%\n表 地\nNYLON 100%\n裏 地')
    assert result['status'] == 'success'
    assert result['selected_part'] == 'outer'
    assert result['parts'] == {'outer': {'cotton': 73, 'polyester': 27}, 'lining': {'nylon': 100}}


@pytest.mark.parametrize('text', [
    '表\n地', '表/地', '表 的', '商品表 地', '表 地番号', '品番: 表 地',
    '表 地 2', '表 地 10%', 'UNKNOWN 表 地', '表 地 UNKNOWN',
])
def test_partial_or_embedded_words_are_not_restored_as_a_heading(text):
    assert normalize_text(text) == text.casefold()


def test_missing_heading_keeps_materials_but_does_not_invent_outer():
    result = analyze_label_text('COTTON 73%\nPOLYESTER 27%')
    assert result['status'] == 'success'
    assert result['selected_part'] == 'generic'
    assert result['materials'] == {'cotton': 73, 'polyester': 27}
    assert result['parse_evidence']['part_resolution'] == {'status': 'unidentified', 'selected_part': 'generic'}


def test_restoring_a_heading_cannot_complete_missing_or_additional_ratios():
    for text in ['表 地\nCOTTON 73%', '表 地\nCOTTON 73%\nPOLYESTER 27%\n10%']:
        result = parse_label(text)
        assert result['status'] == 'failed'
        assert result['materials'] == {}


def test_part_characters_are_not_joined_across_newlines():
    result = analyze_label_text('表\n地\nCOTTON 73%\nPOLYESTER 27%')
    assert result['selected_part'] == 'generic'
    assert result['parse_evidence']['part_resolution']['status'] == 'unidentified'
