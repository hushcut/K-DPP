from dataclasses import replace

import pytest

from apps.text.ocr_corrections import located_generic_rejection_parts, same_region_recovery
from apps.text.ocr_layout import OcrWord, spatial_text_from_words
from apps.text.ocr_text import OcrPayload, _assess_candidates, _build_payload_candidates


def word(text, x, y, width=75):
    return OcrWord(text, x, y, x + width, y + 18)


def build(source, variant, words, raw=None, region=(0, 0, 430, 180)):
    layout = spatial_text_from_words(list(words))
    return _build_payload_candidates(source, OcrPayload(raw or layout, layout_text=layout,
        layout_words=tuple(words)), image_key='same-photo', image_variant_key=variant,
        image_transform=(1, 0, 0, 0, 1, 0), image_region=region)


def repeated_ratios():
    words = (word('OUTER', 0, 0), word('COTTON', 0, 30), word('100', 230, 30),
             word('%', 315, 30, 15), word('LINING', 0, 65),
             word('POLYESTER', 0, 100, 115), word('100', 230, 100), word('%', 315, 100, 15))
    return build('original', 'original-bytes', words,
                 'OUTER\nCOTTON\nLINING\nPOLYESTER\n100%\n100%')


def generic_error():
    source_words = (word('HEADX', 0, 0), word('COTTON', 90, 0),
        word('90', 230, 0), word('%', 315, 0, 15),
        word('LINING', 0, 70), word('POLYESTER', 90, 70, 115),
        word('100', 230, 70), word('%', 315, 70, 15))
    target_words = (replace(source_words[0], text='OUTER'),) + source_words[1:]
    source = build('original', 'first-bytes', source_words)
    target = build('material_crop', 'second-bytes', target_words)
    # Explicitly mark geometry-derived text even when provider text is identical.
    source = [replace(c, layout_used=True) for c in source]
    target = [replace(c, layout_used=True) for c in target]
    return source, target


def test_ratios_read_after_lining_keep_both_real_material_rows():
    raw, layout = repeated_ratios()
    assert 'lining' in raw.unpaired_ratio_parts
    assert same_region_recovery(raw, layout, 'lining')
    decision = _assess_candidates([raw, layout])
    assert decision.status == 'success'
    assert decision.best.parts == {'outer': {'cotton': 100}, 'lining': {'polyester': 100}}
    assert 'lining' not in decision.unpaired_ratio_parts


@pytest.mark.parametrize('failure', [
    'different_photo', 'different_variant', 'different_source', 'missing_boxes',
    'different_boxes', 'missing_percent', 'altered_layout', 'cropped_out_ratio',
    'extra_number_elsewhere', 'unknown_lining', 'existing_wrong_pair',
])
def test_ratio_order_recovery_requires_the_complete_same_response(failure):
    raw, target = repeated_ratios()
    if failure == 'different_photo':
        target = replace(target, image_key='another-photo')
    elif failure == 'different_variant':
        target = replace(target, image_variant_key='another-read')
    elif failure == 'different_source':
        target = replace(target, source='other-provider-response')
    elif failure == 'missing_boxes':
        raw = replace(raw, image_words=())
    elif failure == 'different_boxes':
        target = replace(target, image_words=target.image_words[1:])
    elif failure == 'missing_percent':
        target = replace(target, text=target.text.replace('100 %', '100'))
    elif failure == 'altered_layout':
        target = replace(target, text=target.text.replace('COTTON 100 %', 'POLYESTER 100 %'))
    elif failure == 'cropped_out_ratio':
        target = replace(target, image_region=(0, 0, 200, 180))
        raw = replace(raw, image_region=target.image_region)
    elif failure == 'extra_number_elsewhere':
        extra = word('100', 0, 155)
        raw = replace(raw, image_words=raw.image_words + (extra,), text=raw.text + '\n100')
        target = replace(target, image_words=raw.image_words, text=target.text + '\n100')
    elif failure == 'unknown_lining':
        raw = replace(raw, text=raw.text.replace('POLYESTER', 'OLEFIN'),
            rejected_composition_parts={'lining': ('unresolved_material_token',)})
    elif failure == 'existing_wrong_pair':
        raw = replace(raw, paired_material_ratios={'lining': [('polyester', 90)]})
    assert not same_region_recovery(raw, target, 'lining')


def test_generic_errors_are_preserved_on_the_independently_located_outer():
    source, target = generic_error()
    assert 'generic' in source[0].rejected_composition_parts
    assert located_generic_rejection_parts(source[0], source + target) == ('outer',)
    decision = _assess_candidates(source + target)
    assert decision.status == 'success'
    assert decision.best.selected_part == 'lining'
    assert decision.best.materials == {'polyester': 100}
    assert 'generic' not in decision.rejected_composition_parts
    assert set(source[0].rejected_composition_parts['generic']) <= set(
        decision.rejected_composition_parts['outer'])


@pytest.mark.parametrize('failure', [
    'different_photo', 'same_variant', 'missing_variant', 'missing_source_boxes',
    'missing_target_boxes', 'uncovered_fiber', 'another_page', 'unknown_below_lining',
    'wrong_lining', 'no_outer_heading', 'forged_layout_order', 'additional_unlocated_material',
    'missing_source_variant', 'missing_source_region', 'target_heading_outside_region',
])
def test_generic_error_cannot_be_hidden_by_a_lining_crop(failure):
    source, target = generic_error()
    original, alternative = source[0], target[0]
    if failure == 'different_photo':
        alternative = replace(alternative, image_key='another-photo')
    elif failure == 'same_variant':
        alternative = replace(alternative, image_variant_key=original.image_variant_key)
    elif failure == 'missing_variant':
        alternative = replace(alternative, image_variant_key='')
    elif failure == 'missing_source_boxes':
        original = replace(original, image_words=())
    elif failure == 'missing_target_boxes':
        alternative = replace(alternative, image_words=())
    elif failure == 'uncovered_fiber':
        alternative = replace(alternative, image_region=(0, 60, 430, 180))
    elif failure == 'another_page':
        alternative = replace(alternative, image_words=tuple(replace(w, page=1) for w in alternative.image_words))
    elif failure == 'unknown_below_lining':
        original = replace(original, image_words=tuple(replace(w, top=w.top + 130, bottom=w.bottom + 130)
            for w in original.image_words))
    elif failure == 'wrong_lining':
        alternative = replace(alternative, parts={'lining': {'cotton': 100}})
    elif failure == 'no_outer_heading':
        alternative = replace(alternative, text=alternative.text.replace('OUTER', 'BODY'))
    elif failure == 'forged_layout_order':
        alternative = replace(alternative, text='\n'.join(reversed(alternative.text.splitlines())))
    elif failure == 'additional_unlocated_material':
        original = replace(original, text='OLEFIN 50%\n' + original.text)
    elif failure == 'missing_source_variant':
        original = replace(original, image_variant_key='')
    elif failure == 'missing_source_region':
        original = replace(original, image_region=())
    elif failure == 'target_heading_outside_region':
        alternative = replace(alternative, image_words=tuple(
            replace(w, left=500, right=575) if w.text == 'OUTER' else w
            for w in alternative.image_words))
    assert not located_generic_rejection_parts(original, [original, alternative])


def test_unknown_row_aligned_with_lining_keeps_its_rejection_on_lining():
    source, target = generic_error()
    original, alternative = source[0], target[0]
    # A source without a readable marker spans both rows. Its invalid row
    # is physically beside the target lining and cannot become an outer error.
    moved = tuple(replace(w, top=w.top + 70, bottom=w.bottom + 70)
                  for w in original.image_words)
    original = replace(original, image_words=moved)
    assert located_generic_rejection_parts(original, [original, alternative]) == ('lining',)
    assert _assess_candidates([original, alternative]).status == 'failed'


def damaged_upper_headings():
    words = (word('HEADX', 0, 0), word('COTTON', 90, 0), word('90', 230, 0), word('%', 315, 0, 15),
        word('색', 25, 40, 20), word('2', 50, 40, 15), word('POLYESTER', 90, 40, 115),
        word('100', 230, 40), word('%', 315, 40, 15),
        word('LINING', 0, 90), word('POLYESTER', 90, 90, 115), word('100', 230, 90), word('%', 315, 90, 15))
    raw = 'HEADX COTTON 90%\n색2 POLYESTER\nLINING POLYESTER\n100%\n100%'
    source = build('original', 'first-bytes', words, raw)
    reread_words = (replace(words[0], text='OUTER'),) + words[1:] + (word('배', 0, 40, 15),)
    reread = [replace(c, layout_used=True) for c in build('material_crop', 'second-bytes', reread_words)]
    return source, reread


def test_damaged_upper_heading_ratios_need_independent_part_coordinates():
    source, reread = damaged_upper_headings()
    assert same_region_recovery(source[0], source[1], 'lining', source + reread)
    result = _assess_candidates(source + reread)
    assert result.status == 'success'
    assert result.best.parts['lining'] == {'polyester': 100}
    assert 'lining' not in result.unpaired_ratio_parts
    assert 'outer' in result.rejected_composition_parts
    assert set(source[0].rejected_composition_parts['generic']) <= set(
        result.rejected_composition_parts['outer'])


def test_repeated_ratios_with_unconfirmed_upper_heading_stay_unresolved():
    source, _ = damaged_upper_headings()
    assert not same_region_recovery(source[0], source[1], 'lining', source)
    assert _assess_candidates(source).status == 'failed'


def test_upper_crop_cannot_discard_uncovered_unknown_evidence():
    source, reread = damaged_upper_headings()
    reread = [replace(c, image_region=(0, 30, 430, 180)) for c in reread]
    assert not same_region_recovery(source[0], source[1], 'lining', source + reread)
    assert _assess_candidates(source + reread).status == 'failed'
