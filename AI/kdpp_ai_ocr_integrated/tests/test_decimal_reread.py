"""좌표와 독립 응답으로 확인된 점 오독만 후보 사이에서 해소한다."""

from dataclasses import replace

import pytest

from apps.text.ocr_corrections import same_region_recovery
from apps.text.ocr_layout import OcrWord
from apps.text.ocr_text import OcrPayload, _assess_candidates, _build_payload_candidates


def readings(source_text='Polyester 95%\nPolyurethane.5%'):
    first = (OcrWord('Polyester', 10, 10, 110, 32),
             OcrWord('95', 140, 10, 160, 32), OcrWord('%', 160, 10, 175, 32))
    second = (OcrWord('Polyurethane', 10, 50, 220, 72),
              OcrWord('5', 225, 50, 245, 72), OcrWord('%', 245, 50, 260, 72))
    source_words = first + (OcrWord('Polyurethane.5', 10, 50, 245, 72), second[-1])
    common = {'image_key': 'same-photo', 'image_transform': (1, 0, 0, 0, 1, 0),
              'image_region': (0, 0, 300, 100)}
    source = _build_payload_candidates('original', OcrPayload(
        source_text, layout_text=source_text.replace('%', ' %'), layout_words=source_words),
        image_variant_key='original-read', **common)
    targets = []
    for name, variant, percent in [('preprocessed', 'enhanced-read', False),
                                   ('material_crop', 'cropped-read', True)]:
        text = 'Polyester 95' + ('%' if percent else '') + '\nPolyurethane 5%'
        targets.extend(_build_payload_candidates(name, OcrPayload(
            text, layout_text=text.replace('%', ' %'), layout_words=(first if percent else first[:2]) + second),
            image_variant_key=variant, **common))
    return source, targets


def period_readings():
    source, targets = readings()
    text = 'Polyester 95% .\nPolyurethane'
    words = tuple(w for w in source[0].image_words if w.top == 10) + (
        OcrWord('.', 176, 10, 182, 32), OcrWord('Polyurethane', 10, 50, 220, 72))
    source = _build_payload_candidates('material_crop_rotated', OcrPayload(
        text, layout_text=text.replace('%', ' %'), layout_words=words), image_key='same-photo',
        image_variant_key='rotated-read', image_transform=(1, 0, 0, 0, 1, 0),
        image_region=(0, 0, 300, 100))
    return source, targets


def rebuild(candidate):
    return _build_payload_candidates(candidate.source, OcrPayload(
        candidate.text, layout_words=candidate.image_words),
        image_key=candidate.image_key, image_variant_key=candidate.image_variant_key,
        image_transform=(1, 0, 0, 0, 1, 0), image_region=candidate.image_region)[0]


def test_fused_leading_decimal_requires_independent_explicit_rereads():
    source, targets = readings()
    assert all(c.parser_status == 'failed' for c in source)
    assert all(c.parser_status == 'success' for c in targets)
    for c in source:
        assert same_region_recovery(c, targets[-1], 'generic', source + targets)
    result = _assess_candidates(source + targets)
    assert result.status == 'success'
    assert result.best.materials == {'polyester': 95, 'polyurethane': 5}


@pytest.mark.parametrize('failure', [
    'single_response', 'raw_layout_same_response', 'same_variant', 'same_source',
    'different_photo', 'no_geometry', 'outside_crop', 'missing_source_percent',
    'missing_confirmation_percent', 'moved_confirmation_number', 'moved_confirmation_name',
    'moved_confirmation_percent', 'confirmation_ratio_disagrees', 'extra_source_ratio',
    'unknown_material', 'explicit_zero', 'other_decimal', 'second_changed_number',
])
def test_decimal_recovery_keeps_uncertain_evidence(failure):
    source, targets = readings()
    if failure == 'single_response':
        targets = [targets[-1]]
    elif failure == 'raw_layout_same_response':
        targets = targets[-2:]
    elif failure == 'same_variant':
        targets = [replace(c, image_variant_key='one-response') for c in targets]
    elif failure == 'same_source':
        targets = [replace(c, source='one-source') for c in targets]
    elif failure == 'different_photo':
        targets = [replace(c, image_key='different-photo') if c.source == 'preprocessed' else c for c in targets]
    elif failure == 'no_geometry':
        source = [replace(c, image_words=()) for c in source]
    elif failure == 'outside_crop':
        targets = [replace(c, image_region=(0, 0, 240, 100)) for c in targets]
    elif failure == 'missing_source_percent':
        source = [replace(c, text=c.text.replace('.5%', '.5'), image_words=tuple(
            w for w in c.image_words if not (w.text == '%' and w.top == 50))) for c in source]
    elif failure == 'missing_confirmation_percent':
        targets = [replace(c, text=c.text.replace('5%', '5'), image_words=tuple(
            w for w in c.image_words if not (w.text == '%' and w.top == 50)))
            if c.source == 'preprocessed' else c for c in targets]
    elif failure.startswith('moved_confirmation_'):
        chosen = {'moved_confirmation_number': '5', 'moved_confirmation_name': 'Polyurethane',
                  'moved_confirmation_percent': '%'}[failure]
        targets = [replace(c, image_words=tuple(
            replace(w, top=80, bottom=99) if w.text == chosen and w.top == 50 else w
            for w in c.image_words)) if c.source == 'preprocessed' else c for c in targets]
    elif failure == 'confirmation_ratio_disagrees':
        targets = [replace(c, parts={'generic': {'polyester': 94, 'polyurethane': 6}})
                   if c.source == 'preprocessed' else c for c in targets]
    elif failure == 'extra_source_ratio':
        source = [replace(c, text=c.text + '\n10%', image_words=c.image_words
                          + (OcrWord('10%', 10, 80, 70, 99),)) for c in source]
    elif failure == 'unknown_material':
        source = [replace(c, text=c.text.replace('Polyurethane', 'UNKNOWN'), image_words=tuple(
            replace(w, text='UNKNOWN.5') if w.text == 'Polyurethane.5' else w for w in c.image_words)) for c in source]
    elif failure in ('explicit_zero', 'other_decimal'):
        value = '0.5' if failure == 'explicit_zero' else '1.5'
        source = [replace(c, text=c.text.replace('.5', ' ' + value), image_words=tuple(
            replace(w, text='Polyurethane ' + value) if w.text == 'Polyurethane.5' else w
            for w in c.image_words)) for c in source]
    else:
        source = [replace(c, text=c.text.replace('95', '85'), image_words=tuple(
            replace(w, text='85') if w.text == '95' else w for w in c.image_words)) for c in source]
    source = [rebuild(c) for c in source]
    assert not same_region_recovery(source[0], targets[-1], 'generic', source + targets)
    assert _assess_candidates(source + targets).status == 'failed'


def test_fractional_ratios_are_not_rounded_into_an_integer_composition():
    source, targets = readings()
    words = (OcrWord('Polyester', 10, 10, 110, 32), OcrWord('99.5%', 140, 10, 175, 32),
             OcrWord('Polyurethane.5', 10, 50, 245, 72), OcrWord('%', 245, 50, 260, 72))
    source = _build_payload_candidates('original', OcrPayload(
        'Polyester 99.5%\nPolyurethane.5%', layout_words=words), image_key='same-photo',
        image_variant_key='original-read', image_transform=(1, 0, 0, 0, 1, 0),
        image_region=(0, 0, 300, 100))
    assert source[0].materials == {'polyester': 99.5, 'polyurethane': 0.5}
    assert not same_region_recovery(source[0], targets[-1], 'generic', source + targets)
    assert _assess_candidates(source + targets).status == 'failed'


def test_detached_period_after_percent_preserves_the_ratio_and_missing_fiber():
    source, targets = period_readings()
    for c in source:
        assert same_region_recovery(c, targets[-1], 'generic', source + targets)
    assert _assess_candidates(source + targets).status == 'success'


@pytest.mark.parametrize('failure', [
    'before_percent', 'far_right', 'different_row', 'different_ratio',
    'missing_source_percent', 'missing_target_percent', 'extra_number', 'unknown_translation',
])
def test_period_recovery_does_not_erase_other_evidence(failure):
    source, targets = period_readings()
    if failure == 'before_percent':
        source = [replace(c, text=c.text.replace('95% .', '95. %').replace('95 % .', '95. %'), image_words=tuple(
            replace(w, left=158, right=161, vertices=()) if w.text == '.' else w for w in c.image_words)) for c in source]
    elif failure in ('far_right', 'different_row'):
        source = [replace(c, image_words=tuple(
            replace(w, left=250, right=260, vertices=()) if failure == 'far_right' and w.text == '.' else
            replace(w, top=50, bottom=72, vertices=()) if w.text == '.' else w for w in c.image_words)) for c in source]
    elif failure == 'different_ratio':
        source = [replace(c, text=c.text.replace('95', '90'), image_words=tuple(
            replace(w, text='90') if w.text == '95' else w for w in c.image_words)) for c in source]
    elif failure == 'missing_source_percent':
        source = [replace(c, text=c.text.replace('%', ''), image_words=tuple(
            w for w in c.image_words if w.text != '%')) for c in source]
    elif failure == 'missing_target_percent':
        targets = targets[:2]
    else:
        if failure == 'extra_number':
            source = [replace(c, text=c.text + '\n10%', image_words=c.image_words
                              + (OcrWord('10%', 10, 80, 70, 99),)) for c in source]
        else:
            source = [replace(c, text=c.text + ' aaly', image_words=c.image_words
                              + (OcrWord('aaly', 225, 50, 270, 72),)) for c in source]
    source = [rebuild(c) for c in source]
    assert not same_region_recovery(source[0], targets[-1], 'generic', source + targets)


def test_two_period_artifacts_can_be_resolved_without_changing_two_ratios():
    fused, targets = readings()
    detached, _ = period_readings()
    assert _assess_candidates(fused + detached + targets).status == 'success'
