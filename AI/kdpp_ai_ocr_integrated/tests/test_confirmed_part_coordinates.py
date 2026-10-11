"""A lining fallback cannot erase damage from a different image or part."""
from dataclasses import replace
import pytest
from apps.text.ocr_corrections import located_generic_rejection_parts
from apps.text.ocr_layout import OcrWord, spatial_text_from_words
from apps.text.ocr_text import OcrPayload, _assess_candidates, _build_payload_candidates

def word(text, x, y, width=75):
    return OcrWord(text, x, y, x + width, y + 18)

def build(source, variant, words, raw=None, region=(0, 0, 430, 180)):
    layout = spatial_text_from_words(list(words))
    return _build_payload_candidates(source, OcrPayload(raw or layout, layout_text=layout,
        layout_words=tuple(words)), image_key='same-photo', image_variant_key=variant,
        image_transform=(1, 0, 0, 0, 1, 0), image_region=region)

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
