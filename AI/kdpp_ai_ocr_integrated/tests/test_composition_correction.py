from dataclasses import replace
from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from apps.text.ocr_image import ocr_coordinate_frame, preprocess_rotated_image_bytes
from apps.text.ocr_layout import OcrWord
from apps.text.ocr_text import OcrPayload, _assess_candidates, _build_payload_candidates
from apps.text.parse_label import parse_label


@pytest.mark.parametrize('text, expected', [
    ('Cotton 95%\nSpan 5%', {'cotton': 95, 'spandex': 5}),
    ('Polyester 75%\nRayon 21%\nSPAN 4%', {'polyester': 75, 'rayon': 21, 'spandex': 4}),
    ('94%\nCotton\n6% Spandex', {'cotton': 94, 'spandex': 6}),
    ('94% MERCERIZED\nCOTTON\n6% SPANDEX', {'cotton': 94, 'spandex': 6}),
    ('94% MERCERIZED COTTON\n6% SPANDEX', {'cotton': 94, 'spandex': 6}),
    ('94%\nmercerized cotton\nspandex 6%', {'cotton': 94, 'spandex': 6}),
    ('OUTER\n94%\nCotton\nSpan 6%\nLINING Polyester 100%', {'cotton': 94, 'spandex': 6}),
    ('Cotton 60%\n40%\nSPAN', {'cotton': 60, 'spandex': 40}),
])
def test_registered_names_and_mixed_leading_ratio_rows(text, expected):
    parsed = parse_label(text)
    assert parsed['status'] == 'success'
    assert parsed['materials'] == expected


@pytest.mark.parametrize('text', [
    'Spanish 100%', 'Timespan 100%', 'Spanner 100%',
    '94%\nCotton\n6%', '94%\nCotton 6%',
    '94%\nCotton\nLINING Span 6%', '94%\nCotton\nUnknown 6%',
    '94% MERCERIZED\nMODACRYLIC\n6% SPANDEX',
    '94% FAUX\nCOTTON\n6% SPANDEX',
    '94% MERCERIZED\nCOTTON X\n6% SPANDEX',
    '94% MERCERIZED\nCOTTON\n6% SPANDEX\n10%',
    '94%\nCotton\n7% Spandex',
])
def test_leading_ratio_repair_preserves_incomplete_and_unknown_evidence(text):
    assert parse_label(text)['status'] == 'failed'


def words(ratio='5%', material='Polyester', offset=0):
    return (OcrWord(material, 10, 10 + offset, 110, 30 + offset),
            OcrWord(ratio, 250, 10 + offset, 290, 30 + offset),
            OcrWord('Rayon', 10, 50 + offset, 110, 70 + offset),
            OcrWord('21%', 250, 50 + offset, 290, 70 + offset),
            OcrWord('Span', 10, 90 + offset, 110, 110 + offset),
            OcrWord('4%', 250, 90 + offset, 290, 110 + offset))


def candidates(text, image_words, source='original', key='same-image', region=(0, 0, 400, 400)):
    return _build_payload_candidates(source, OcrPayload(text, layout_words=image_words),
                                     image_key=key, image_transform=(1, 0, 0, 0, 1, 0), image_region=region)


def test_same_position_reread_resolves_a_dropped_digit_without_rescaling():
    original = candidates('Polyester 5%\nRayon 21%\nSpan 4%', words())
    corrected = candidates('Polyester 75%\nRayon 21%\nSpan 4%', words('75%'), 'rotated')
    decision = _assess_candidates(original + corrected)
    assert decision.status == 'success'
    assert decision.best.materials == {'polyester': 75, 'rayon': 21, 'spandex': 4}
    assert decision.rejected_composition_parts == {}
    assert decision.unpaired_ratio_parts == ()


@pytest.mark.parametrize('layout', [False, True])
def test_single_digit_and_percent_words_remain_locatable_in_ratio_only_rows(layout):
    original_words, corrected_words = [], []
    for material, original_ratio, correct_ratio, y in [('Polyester', '5', '75', 10), ('Rayon', '21', '21', 50), ('Span', '4', '4', 90)]:
        for collection, ratio in [(original_words, original_ratio), (corrected_words, correct_ratio)]:
            collection.extend([OcrWord(material, 10, y, 110, y + 20),
                               OcrWord(ratio, 250, y, 280, y + 20), OcrWord('%', 280, y, 290, y + 20)])
    raw = 'Polyester\n5%\nRayon\n21%\nSpan\n4%'
    corrected = 'Polyester\n75%\nRayon\n21%\nSpan\n4%'
    if layout:
        raw, corrected = raw.replace('\n5', ' 5').replace('\n21', ' 21').replace('\n4', ' 4'), corrected.replace('\n75', ' 75').replace('\n21', ' 21').replace('\n4', ' 4')
    decision = _assess_candidates(candidates(raw, tuple(original_words)) + candidates(corrected, tuple(corrected_words), 'rotated'))
    assert decision.status == 'success'


@pytest.mark.parametrize('failure', ['no_geometry', 'different_image', 'different_position', 'cropped_out_row', 'different_digit'])
def test_changed_ratio_requires_same_image_coverage_and_literal_digit_recovery(failure):
    original = candidates('Polyester 5%\nRayon 21%\nSpan 4%', words())
    corrected = candidates('Polyester 75%\nRayon 21%\nSpan 4%', words('75%'), 'rotated')
    if failure == 'no_geometry':
        original = [replace(c, image_words=()) for c in original]
    elif failure == 'different_image':
        corrected = [replace(c, image_key='other-image') for c in corrected]
    elif failure == 'different_position':
        corrected = candidates('Polyester 75%\nRayon 21%\nSpan 4%', words('75%', offset=200), 'rotated')
    elif failure == 'cropped_out_row':
        corrected = [replace(c, image_region=(0, 0, 400, 80)) for c in corrected]
    else:
        original = candidates('Polyester 65%\nRayon 21%\nSpan 4%', words('65%'))
    assert _assess_candidates(original + corrected).status == 'failed'


@pytest.mark.parametrize('material, ratio', [('OLEFIN', '75%'), ('MODACRYLIC', '75%'),
                                           ('FAUX', '75%'), ('UNKNOWN', '75%'), ('Polyester', '-5%')])
def test_registered_success_does_not_hide_unknown_fiber_or_negative_ratio(material, ratio):
    original = candidates(f'{material} {ratio}\nRayon 21%\nSpan 4%', words(ratio, material))
    corrected = candidates('Polyester 75%\nRayon 21%\nSpan 4%', words('75%'), 'rotated')
    assert _assess_candidates(original + corrected).status == 'failed'


def test_complete_conflicting_rereads_remain_conflicting():
    original_words = list(words('70%'))
    original_words[3] = replace(original_words[3], text='26%')
    original = candidates('Polyester 70%\nRayon 26%\nSpan 4%', tuple(original_words))
    corrected = candidates('Polyester 75%\nRayon 21%\nSpan 4%', words('75%'), 'rotated')
    decision = _assess_candidates(original + corrected)
    assert decision.status == 'failed'
    assert decision.conflicting_parts == ('generic',)


def test_reread_does_not_discard_an_extra_ratio_row():
    original_words = words() + (OcrWord('10%', 250, 150, 290, 170),)
    original = candidates('Polyester 5%\nRayon 21%\nSpan 4%\n10%', original_words)
    corrected = candidates('Polyester 75%\nRayon 21%\nSpan 4%', words('75%'), 'rotated')
    assert _assess_candidates(original + corrected).status == 'failed'


def test_same_position_reread_recovers_missing_hundred():
    original_words = (OcrWord('polyester', 50, 20, 250, 40), OcrWord('%', 100, 100, 120, 130))
    corrected_words = original_words + (OcrWord('100', 100, 50, 160, 80),)
    original = candidates('polyester\n%', original_words)
    corrected = candidates('polyester\n100\n%', corrected_words, 'preprocessed')
    assert _assess_candidates(original + corrected).status == 'success'


def test_impossible_four_digit_row_needs_a_matching_valid_reread():
    original = candidates('KAY 1100%', (OcrWord('KAY', 40, 20, 220, 50), OcrWord('1100%', 240, 20, 340, 50)))
    corrected = candidates('KR 겉감 면 100%', (OcrWord('KR', 40, 20, 80, 50),
                                             OcrWord('겉감', 90, 20, 150, 50),
                                             OcrWord('면', 185, 20, 220, 50),
                                             OcrWord('100%', 245, 20, 340, 50)), 'preprocessed')
    assert _assess_candidates(original + corrected).status == 'success'


def test_one_letter_material_recovery_needs_a_reread_in_the_same_location():
    original = candidates('Polgester 75%\nRayon 21%\nSpan 4%', words('75%', 'Polgester'), 'reflection')
    corrected = candidates('Polyester 75%\nRayon 21%\nSpan 4%', words('75%'), 'rotated')
    assert _assess_candidates(original + corrected).status == 'success'


def test_rotation_coordinate_map_tracks_actual_pillow_pixels():
    image = Image.new('RGB', (300, 180), 'white')
    ImageDraw.Draw(image).rectangle((100, 60, 130, 90), fill='black')
    buffer = BytesIO()
    image.save(buffer, format='PNG')
    original = buffer.getvalue()
    processed = preprocess_rotated_image_bytes(original)
    transform, _region = ocr_coordinate_frame(original, processed, 'rotated')
    with Image.open(BytesIO(processed)) as rotated:
        bbox = rotated.convert('L').point(lambda value: 255 if value < 80 else 0).getbbox()
    x, y = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    a, b, c, d, e, f = transform
    assert a * x + b * y + c == pytest.approx(115, abs=2)
    assert d * x + e * y + f == pytest.approx(75, abs=2)


def test_unhandled_exif_orientation_has_no_correction_frame():
    image = Image.new('RGB', (30, 18), 'white')
    exif = image.getexif()
    exif[274] = 6
    buffer = BytesIO()
    image.save(buffer, format='JPEG', exif=exif)
    assert ocr_coordinate_frame(buffer.getvalue(), buffer.getvalue(), 'original') is None


def test_crop_must_cover_whole_source_words_not_only_their_centers():
    original = candidates('Polyester 5%\nRayon 21%\nSpan 4%', words())
    corrected = candidates('Polyester 75%\nRayon 21%\nSpan 4%', words('75%'), 'rotated', region=(40, 0, 400, 400))
    assert _assess_candidates(original + corrected).status == 'failed'


@pytest.mark.parametrize('confirmation', ['distinct_input', 'same_input', 'same_method', 'different_location'])
def test_digit_substitution_requires_two_distinct_aligned_image_conditions(confirmation):
    original = candidates('Polyester 74%\nRayon 21%\nSpan 4%', words('74%'))
    first = [replace(c, image_variant_key='first-input') for c in candidates(
        'Polyester 75%\nRayon 21%\nSpan 4%', words('75%'), 'rotated')]
    second = [replace(c, image_variant_key='second-input') for c in candidates(
        'Polyester 75%\nRayon 21%\nSpan 4%', words('75%'), 'preprocessed')]
    if confirmation == 'same_input':
        second = [replace(c, image_variant_key='first-input') for c in second]
    elif confirmation == 'same_method':
        second = [replace(c, source='rotated') for c in second]
    elif confirmation == 'different_location':
        second = [replace(c, image_variant_key='second-input') for c in candidates(
            'Polyester 75%\nRayon 21%\nSpan 4%', words('75%', offset=200), 'preprocessed')]
    decision = _assess_candidates(original + first + second)
    assert decision.status == ('success' if confirmation == 'distinct_input' else 'failed')

@pytest.mark.parametrize('material', ['Cotton', '면'])
@pytest.mark.parametrize('compact', [False, True])
@pytest.mark.parametrize('ratio', ['50', '5'])
def test_attached_numeric_evidence_cannot_jump_to_hundred(material, compact, ratio):
    separator = '' if compact else ' '
    original_words = (OcrWord(material, 10, 10, 110, 30),
                      OcrWord(ratio, 200, 10, 230, 30), OcrWord('%', 230, 10, 250, 30))
    corrected_words = (original_words[0], OcrWord('100', 200, 10, 230, 30), original_words[2])
    original = candidates(f'{material}{separator}{ratio}%', original_words)
    corrected = candidates(f'{material} 100%', corrected_words, 'preprocessed')
    assert _assess_candidates(original + corrected).status == 'failed'


@pytest.mark.parametrize('material', ['Cotton', '면'])
@pytest.mark.parametrize('missing_from', ['original', 'corrected'])
def test_numeric_evidence_requires_every_number_box(material, missing_from):
    original_words = (OcrWord(material, 10, 10, 110, 30),
                      OcrWord('50', 200, 10, 230, 30), OcrWord('%', 230, 10, 250, 30))
    corrected_words = (original_words[0], OcrWord('100', 200, 10, 230, 30), original_words[2])
    if missing_from == 'original':
        original_words = (original_words[0], original_words[2])
    else:
        corrected_words = (corrected_words[0], corrected_words[2])
    original = candidates(f'{material} 50%', original_words)
    corrected = candidates(f'{material} 100%', corrected_words, 'preprocessed')
    assert _assess_candidates(original + corrected).status == 'failed'


@pytest.mark.parametrize('material', ['Cotton', '면'])
def test_repeated_numeric_evidence_cannot_reuse_one_number_box(material):
    image_words = (OcrWord(material, 10, 10, 110, 30),
                   OcrWord('100', 200, 10, 230, 30), OcrWord('%', 230, 10, 250, 30))
    original = candidates(f'{material} 100% 100%', image_words)
    corrected = candidates(f'{material} 100%', image_words, 'preprocessed')
    assert _assess_candidates(original + corrected).status == 'failed'


@pytest.mark.parametrize('compact_target', [False, True])
def test_attached_numeric_evidence_keeps_verified_dropped_digit_recovery(compact_target):
    original = candidates('Polyester5%\nRayon21%\nSpan4%', words())
    text = 'Polyester75%\nRayon21%\nSpan4%' if compact_target else 'Polyester 75%\nRayon 21%\nSpan 4%'
    corrected = candidates(text, words('75%'), 'rotated')
    decision = _assess_candidates(original + corrected)
    assert decision.status == 'success'
    assert decision.best.materials == {'polyester': 75, 'rayon': 21, 'spandex': 4}
