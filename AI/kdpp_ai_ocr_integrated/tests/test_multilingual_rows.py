"""Complete primary compositions and corrupted translated copies stay distinct.

Translation and care-number tests come from kyh/ai d87f145 and still pass on the
current integration. The recorded-candidate checks are rewritten for the current
safety policy (see AI_최종평가_20261015.md, 2026-10-21 후보 묶음 교차 검증).
"""
from collections import Counter
from dataclasses import replace
import json
from pathlib import Path

import pytest

from apps.text import ocr_text
from apps.text.ocr_corrections import _has_unclassified_context, same_region_recovery
from apps.text.ocr_layout import OcrWord
from apps.text.parse_label import parse_label


@pytest.mark.parametrize('text,materials', [
    ('100% Cotton/Coton/Baumwolle/XXX/コットン', {'cotton': 100}),
    ('33% Cotton/Coton/Bau\nmwolle/Algod\não/ji/コットン\n'
     '62% Polyester/Poliéste/ポリエステル\n5% Elastane/Élasthann\ne/Elasthan/XXX',
     {'cotton': 33, 'polyester': 62, 'spandex': 5}),
    ('YARN\nUK:100% POLYESTER IT:100% POLIESTERE\n'
     'EL:100% ПOAYEΣTEPA JP:100% 刹工万元 CN:100% 聚酯纤维', {'polyester': 100}),
])
def test_complete_primary_keeps_unread_translation_warning(text, materials):
    result = parse_label(text)
    assert result['status'] == 'success', result
    assert result['materials'] == materials
    assert 'unread_translation_rows' in result['warnings']
    assert result['confidence']['parser'] == 'medium'
    assert result['confidence']['ocr'] == 'unknown'
    assert result['raw_ocr_preview'].startswith(text.splitlines()[0])


@pytest.mark.parametrize('text', [
    '100% Cotton/Coton/Nylon',
    '100% Cotton/Coton/UNKNOWN',
    '100% Cotton/Coton/OLEFIN',
    '100% Cotton/Coton/MODACRYLIC',
    '100% Cotton/Coton/木纤维',
    '100% Cotton/Coton/XXX 10%',
    '100% Cotton/Coton/XXX 10',
    '100% Cotton/Coton/-10%',
    '70% Cotton/Coton/XXX',
    '100% Cotton/XXX',
    '100% POLY/Coton/XXX',
    '100% XXX/Coton/Baumwolle',
    'EN:100% POLYESTER FR:100% NYLON JP:100% 刹工万元',
    'EN:100% POLYESTER FR:100% POLIESTERE JP:95% 刹工万元',
    'EN:100% POLYESTER FR:100% POLIESTERE JP:100% UNKNOWN',
    'EN:100% POLYESTER FR:100% POLIESTERE JP:100% MODACRYLIC',
    'EN:100% POLYESTER FR:100% POLIESTERE JP:100% 木纤维',
    'EN:100% POLYESTER FR:100% POLIESTERE JP:100% 刹工万元 20',
    'EN:100% POLYESTER FR:100% POLIESTERE JP:100% 刹工万元 10%',
    'EN:100% POLYESTER FR:100% POLIESTERE JP:~100% 刹工万元',
    'EN:100% POLYESTER FR:100% POLIESTERE JP:-100% 刹工万元',
    'EN:100% XXX FR:100% POLYESTER IT:100% POLIESTERE',
    'EN:100% POLYESTER JP:100% 刹工万元',
    '100% Cotton/Coton/XXX\nLINING\n40%',
])
def test_translation_cannot_invent_primary_or_hide_conflicting_evidence(text):
    result = parse_label(text)
    # A complete outer composition may retain an explicitly separate, missing
    # lining; this case checks part ownership rather than forcing outer failure.
    if '\nLINING\n' in text:
        assert result['selected_part'] == 'generic'
        assert result['materials'] == {'cotton': 100}
        assert 'lining' not in result['parts']
    else:
        assert result['status'] == 'failed', result

def care_readings():
    words = (OcrWord('100%', 10, 10, 45, 30), OcrWord('Cotton', 50, 10, 105, 30),
             OcrWord('/', 106, 10, 110, 30), OcrWord('Coton', 115, 10, 160, 30),
             OcrWord('/', 161, 10, 165, 30), OcrWord('XXX', 170, 10, 200, 30),
             OcrWord('30', 20, 60, 40, 80), OcrWord('HAND', 10, 95, 45, 115),
             OcrWord('WASH', 50, 95, 95, 115))
    text = '100% Cotton/Coton/XXX\n30\nHAND WASH'
    common = {'image_key': 'same', 'image_variant_key': 'whole', 'image_words': words,
              'image_region': (0, 0, 220, 130)}
    target = replace(ocr_text._build_candidate('original', text), **common)
    source = replace(ocr_text._build_candidate('material_crop', text.split('HAND')[0]),
        **{**common, 'image_variant_key': 'crop'})
    return source, target


def test_care_number_requires_same_original_pixel_location():
    source, target = care_readings()
    assert source.parser_status == 'failed'
    assert target.parser_status == 'success'
    assert same_region_recovery(source, target, 'generic')
    assert ocr_text._assess_candidates([source, target]).status == 'success'


@pytest.mark.parametrize('error', ['different_image', 'missing_words', 'moved_care',
    'moved_primary', 'outside_care_region', 'explicit_percent', 'extra_number', 'swapped_ratio', 'unknown_fiber', 'part'])
def test_care_recovery_cannot_reassign_materials_or_add_percentages(error):
    source, target = care_readings()
    if error == 'different_image':
        target = replace(target, image_key='other')
    elif error == 'missing_words':
        source = replace(source, image_words=())
    elif error in {'moved_care', 'moved_primary'}:
        changed = '30' if error == 'moved_care' else 'Cotton'
        source = replace(source, image_words=tuple(replace(w, left=w.left+500, right=w.right+500)
            if w.text == changed else w for w in source.image_words))
    elif error == 'outside_care_region':
        target = replace(target, image_region=(0, 0, 220, 40))
    elif error == 'explicit_percent':
        source = replace(source, text=source.text.replace('\n30', '\n30%'))
    elif error == 'extra_number':
        source = replace(source, text=source.text+'\n20%')
    elif error == 'swapped_ratio':
        source = replace(source, text=source.text.replace('100%', '70%'))
    elif error == 'unknown_fiber':
        source = replace(source, text=source.text+'\nUNKNOWN 20%')
    else:
        target = replace(target, parts={'lining': target.parts['generic']})
    assert not same_region_recovery(source, target, 'generic')



FIXTURE = json.loads((Path(__file__).parent / 'fixtures/candidate_set_cross_check.json').read_text(encoding='utf-8'))
CASES = {case['image_id']: case for case in FIXTURE['cases']}


def restore_candidate(data):
    words = tuple(OcrWord(text, left, top, right, bottom,
                          tuple(zip(flat[0::2], flat[1::2])))
                  for text, left, top, right, bottom, flat in FIXTURE['word_sets'][data['words']])
    return replace(ocr_text._build_candidate(data['source'], data['text'], layout_used=data['layout_used']),
                   image_key=data['image_key'], image_variant_key=data['image_variant_key'],
                   image_words=words, image_region=tuple(data['image_region']))


def assessed(candidates):
    decision = ocr_text._assess_candidates(candidates)
    return parse_label(decision.best.text, conflicting_parts=decision.conflicting_parts,
                       unpaired_ratio_parts=decision.unpaired_ratio_parts,
                       rejected_composition_parts=decision.rejected_composition_parts)


@pytest.mark.parametrize('image_id', sorted(CASES))
def test_current_pipeline_candidates_reach_the_answer(image_id):
    """The candidates the current pipeline builds for these photos are confirmed."""
    case = CASES[image_id]
    result = assessed([restore_candidate(c) for c in case['pipeline_candidates']])
    assert result['status'] == 'success', result
    assert result['materials'] == case['answer']
    assert result['selected_part'] == case['answer_part']


@pytest.mark.parametrize('image_id', ['DJ017', 'DJ031', 'DJ044'])
def test_unclassified_crop_context_keeps_recorded_sets_failed(image_id):
    """A correct reading does not erase a crop whose surrounding text cannot be classified.

    The recorded crop keeps unreadable fragments next to the composition. They may be a
    cut-off caption or a missing fiber name, so the current policy keeps the failure.
    """
    reader, crop = [restore_candidate(c) for c in CASES[image_id]['recorded_candidates']]
    alone = assessed([reader])
    assert alone['status'] == 'success'
    assert alone['materials'] == CASES[image_id]['answer']
    assert _has_unclassified_context(crop)
    assert assessed([reader, crop])['status'] == 'failed'


@pytest.mark.parametrize('image_id', ['DJ022', 'DJ047'])
def test_same_photo_can_differ_by_candidate_set(image_id):
    """The recorded extra candidates keep these photos failed; the pipeline set succeeds."""
    case = CASES[image_id]
    assert assessed([restore_candidate(c) for c in case['recorded_candidates']])['status'] == 'failed'
    assert assessed([restore_candidate(c) for c in case['pipeline_candidates']])['status'] == 'success'


def test_resolvable_damage_in_another_candidate_does_not_block_the_answer():
    """DJ044's preprocessed reading fails alone, but its evidence is resolved at the same location."""
    candidates = [restore_candidate(c) for c in CASES['DJ044']['pipeline_candidates']]
    preprocessed = next(c for c in candidates if c.source == 'preprocessed' and not c.layout_used)
    assert preprocessed.parser_status == 'failed' and preprocessed.rejected_composition_parts
    assert assessed(candidates)['materials'] == CASES['DJ044']['answer']


def test_tagged_layout_failure_needs_same_response_and_every_literal_token():
    raw, layout = [restore_candidate(c) for c in CASES['DJ047']['recorded_candidates']
                   if c['source'] == 'preprocessed']
    assert raw.parser_status == 'success' and layout.parser_status == 'failed'
    assert Counter(raw.image_words) == Counter(layout.image_words)
    assert same_region_recovery(layout, raw, 'embroidery_yarn')
    assert not same_region_recovery(replace(layout, image_variant_key='other'), raw, 'embroidery_yarn')
    assert not same_region_recovery(replace(layout, text=layout.text + '\nNYLON 20%'), raw, 'embroidery_yarn')
