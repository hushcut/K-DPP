"""좌표로 확인한 비율 칸 오독만 복구하는 후보 판정 회귀."""

from dataclasses import replace

import pytest

from apps.text.ocr_corrections import same_region_recovery
from apps.text.ocr_layout import OcrWord
from apps.text.ocr_text import OcrPayload, _assess_candidates, _build_payload_candidates


def readings(glyph='魚'):
    names = (OcrWord('Polyester', 10, 10, 110, 32),
             OcrWord('Rayon', 10, 50, 90, 72), OcrWord('Span', 10, 90, 80, 112))
    ratios = (OcrWord('21', 180, 50, 210, 72), OcrWord('%', 210, 50, 230, 72),
              OcrWord('4', 190, 90, 210, 112), OcrWord('%', 210, 90, 230, 112))
    broken = (OcrWord('&', 180, 10, 194, 32), OcrWord(glyph, 194, 10, 210, 32),
              OcrWord('%', 210, 10, 230, 32))
    good = (OcrWord('75', 180, 10, 210, 32), OcrWord('%', 210, 10, 230, 32))
    common = {'image_key': 'same-photo', 'image_transform': (1, 0, 0, 0, 1, 0),
              'image_region': (0, 0, 250, 130)}
    source = _build_payload_candidates('material_crop', OcrPayload(
        f'Polyester\nRayon\nSpan\n%{glyph}&\n21%\n4%',
        layout_text=f'Polyester & {glyph} %\nRayon 21 %\nSpan 4 %',
        layout_words=names + broken + ratios), image_variant_key='broken-read', **common)
    target = _build_payload_candidates('material_crop_rotated', OcrPayload(
        'Polyester 75%\nRayon 21%\nSpan 4%',
        layout_words=names + good + ratios), image_variant_key='clear-read', **common)[0]
    return source, target


@pytest.mark.parametrize('glyph', ['魚', '?'])
def test_aligned_ratio_column_glyph_is_resolved_for_raw_and_layout(glyph):
    source, target = readings(glyph)
    assert target.parser_status == 'success'
    assert all(c.parser_status == 'failed' for c in source)
    for candidate in source:
        assert same_region_recovery(candidate, target, 'generic', [*source, target])
    decision = _assess_candidates([*source, target])
    assert decision.status == 'success'
    assert decision.best.materials == {'polyester': 75, 'rayon': 21, 'spandex': 4}


@pytest.mark.parametrize('failure', [
    'different_photo', 'no_geometry', 'outside_crop', 'moved_number',
    'swapped_names', 'forged_ratio', 'different_part', 'extra_ratio',
    'unknown_fiber', 'negative_ratio', 'missing_percent', 'duplicate_percent',
    'lost_layout_word', 'different_layout_response',
])
def test_ratio_glyph_recovery_preserves_other_evidence(failure):
    source, target = readings()
    if failure == 'different_photo':
        target = replace(target, image_key='another-photo')
    elif failure == 'no_geometry':
        source = [replace(c, image_words=()) for c in source]
    elif failure == 'outside_crop':
        target = replace(target, image_region=(0, 0, 175, 130))
    elif failure == 'moved_number':
        target = replace(target, image_words=tuple(
            replace(w, top=120, bottom=130) if w.text == '75' else w for w in target.image_words))
    elif failure == 'swapped_names':
        target = replace(target, image_words=tuple(
            replace(w, top=50, bottom=72) if w.text == 'Polyester' else
            replace(w, top=10, bottom=32) if w.text == 'Rayon' else w for w in target.image_words))
    elif failure == 'forged_ratio':
        target = replace(target, parts={'generic': {'polyester': 74, 'rayon': 21, 'spandex': 5}})
    elif failure == 'different_part':
        target = replace(target, parts={'lining': target.parts['generic']})
    elif failure == 'extra_ratio':
        source = [replace(c, text=c.text + '\n10%',
                          image_words=c.image_words + (OcrWord('10%', 10, 115, 70, 129),)) for c in source]
    elif failure == 'unknown_fiber':
        source, target = readings('UNKNOWN')
    elif failure == 'negative_ratio':
        source, target = readings('-')
    elif failure == 'missing_percent':
        source = [replace(c, text=c.text.replace('%魚&', '魚&').replace('& 魚 %', '& 魚'),
                          image_words=tuple(w for w in c.image_words if not (w.text == '%' and w.top == 10))) for c in source]
    elif failure == 'duplicate_percent':
        source = [replace(c, text=c.text.replace('%魚&', '%%魚&').replace('& 魚 %', '& 魚 % %'),
                          image_words=c.image_words + (OcrWord('%', 231, 10, 245, 32),)) for c in source]
    elif failure == 'lost_layout_word':
        source[1] = replace(source[1], text=source[1].text.replace('魚', ''))
    else:
        source[1] = replace(source[1], image_variant_key='unrelated-response')
    assert not same_region_recovery(source[0], target, 'generic', [*source, target])
    assert _assess_candidates([*source, target]).status == 'failed'


def test_glyph_without_token_preserving_layout_peer_is_not_guessed():
    source, target = readings()
    assert not same_region_recovery(source[0], target, 'generic', [source[0], target])


@pytest.mark.parametrize('glyph', ['未知', 'WOOL', 'A', '+', '−'])
def test_material_names_and_signed_glyphs_are_not_numeric_recovery(glyph):
    source, target = readings(glyph)
    assert not same_region_recovery(source[1], target, 'generic', [*source, target])


def test_two_damaged_ratio_cells_cannot_be_invented_together():
    source, target = readings()
    source = [replace(c, text=c.text.replace('21%', '%?&').replace('21 %', '& ? %'),
                      image_words=tuple(w for w in c.image_words if not (w.text == '21'))
                      + (OcrWord('&', 180, 50, 194, 72), OcrWord('?', 194, 50, 210, 72))) for c in source]
    assert not same_region_recovery(source[0], target, 'generic', [*source, target])
    assert _assess_candidates([*source, target]).status == 'failed'


def test_glyph_recovery_cannot_also_change_another_valid_number():
    source, target = readings()
    source = [replace(c, text=c.text.replace('21', '31'),
                      image_words=tuple(replace(w, text='31') if w.text == '21' else w
                                        for w in c.image_words)) for c in source]
    assert not same_region_recovery(source[0], target, 'generic', [*source, target])
    assert _assess_candidates([*source, target]).status == 'failed'
