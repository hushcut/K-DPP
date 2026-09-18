# Synthetic Material-Label Pilot

This experiment creates controlled material-label images and an exact answer manifest with Pillow.
It is isolated from the production OCR path and does not train Google Vision.

## Pilot scope

- 20 base label contents
- 4 visual variants per base label
- 80 images in total
- Korean, English, Japanese, and Chinese labels
- Clean, rotation, blur, low-light, affine perspective, glare, and mixed conditions
- Single-composition and part-based labels such as shell and lining

The generated images are intended for parser regression tests, preprocessing comparisons, and future
local OCR experiments. Real QA photos already used to improve the parser are regression data, not an
unseen final holdout. Final evaluation needs photos not used for development, grouped by original label
or garment so related photos do not cross development and evaluation splits.

## Generate

Run from `AI/kdpp_ai_ocr_integrated`:

```powershell
python scripts/generate_synthetic_labels.py
```

The current default is `outputs/synthetic/synthetic_v1_pilot_corrected_v1_0_3` (generator v1.0.3).
The original v1.0.0 pilot and historical corrected v1.0.2 output stay in their existing directories,
with their own resolved configs.
Reproducing that historical generator also requires its historical code, not just its old config.
Generated output is ignored by Git.
The generator refuses to overwrite a non-empty output directory. Use `--output` for another run:

```powershell
python scripts/generate_synthetic_labels.py --output outputs/synthetic/synthetic_v1_pilot_corrected_run2
```

## Output

- `images/`: generated JPEG files
- `manifest.csv`: exact material, ratio, language, part, layout, and condition answers
- `summary.json`: counts used for a quick integrity check
- `config_resolved.json`: the exact configuration for reproduction
- `contact_sheet.jpg`: visual review sheet

`source_group` identifies images generated from the same base label. If this data is later split for
training, validation, and testing, every row in a source group must stay in the same split. The pilot
manifest deliberately leaves `split` as `unassigned` and `include_in_accuracy` as `false` so it cannot
be mistaken for the real-photo QA score.

Generator v1.0.3 records the sampled composition in `source_parts_json` and the rendered answer
in `parts_json`. The current `material_label_policy` is `kdpp-fiber-labels-v2`. It keeps
`spandex` and `polyurethane` separate in every language: Chinese `氨纶` is `spandex`, while
`聚氨酯` is `polyurethane`. No ratios or material keys are merged. The evaluator still understands
the historical v1 policy so old manifests remain reproducible records, and it rejects a versioned
manifest when its Chinese elastic-fiber marker contradicts the recorded material key.

## Validation and deciding whether more data is needed

1. Inspect `contact_sheet.jpg` and a sample from every language and condition.
2. Confirm each expected composition in `manifest.csv` matches the visible label.
3. Run OCR and parser experiments separately, reporting OCR failure and parsing failure.
4. Keep the real-photo QA score separate from the synthetic-data score.
5. Add only cases needed to cover observed failures. A 400-image expansion is not a required next step.
   More generated photos do not retrain the external Google Vision model.

## Parser-only regression evaluation

```powershell
python scripts/evaluate_synthetic_parser.py --manifest outputs/synthetic/synthetic_v1_pilot/manifest.csv --output outputs/synthetic/parser_alias_review/after.json
python scripts/evaluate_synthetic_parser.py --manifest outputs/synthetic/synthetic_v1_pilot_corrected_v1_0_2/manifest.csv --output outputs/synthetic/pilot_correction_review/corrected.json
python scripts/evaluate_synthetic_parser.py --manifest outputs/synthetic/synthetic_v1_pilot_corrected_v1_0_3/manifest.csv --output outputs/synthetic/synthetic_v1_pilot_corrected_v1_0_3/parser_report.json
```

This reads `original_text` only; it does not open images or call Google Vision.
It reports exact material/ratio matches and selected-part matches separately,
both per image row and per unique `source_group`. All original rows remain in
the denominator, including known label-generation errors. Use `--parser-root`
to compare a separate baseline checkout with the same evaluator.

The unchanged v1.0.0 pilot improved from 60/80 to 72/80 material matches after
Japanese/Chinese parser updates. The remaining two source groups contain the
incorrect Chinese acrylic spelling `腨纶`; source 0020 also exposes the generator's
ambiguous `氨纶` mapping to both spandex and polyurethane. Generator v1.0.1 fixes
the acrylic spelling to `腈纶` for future runs. Generator v1.0.2 records the historical v1
label-key contract and matched 80/80 under that contract. Generator v1.0.3 adopts the current
v2 contract. Its 80 image hashes are identical to v1.0.2, while the four `SYN_SOURCE_0020`
manifest rows now record `acrylic 60, spandex 40`. The v1.0.3 pilot matches 80/80 image rows
(20/20 distinct texts) with the current parser. This is a ground-truth contract correction,
not an OCR-performance gain. Image OCR has not been evaluated yet.

See [the parser review](PARSER_ALIAS_REVIEW.md) for results, limitations, and next steps.
See [the pilot correction review](PILOT_CORRECTION_REVIEW.md) for the contract, exact changes,
preservation checks, and reproduction commands.

## Subsequent material-evidence validation

The parser now requires explicit material/ratio correspondence and a complete 100% composition.
It preserves decimal ratios, rejects missing or contradictory evidence, and keeps a failed outer
part from being replaced with a valid lining. The current v1.0.3 pilot remains 80/80. The
historical v1.0.2 manifest is retained as a legacy-contract record; its four `氨纶` rows
intentionally differ from the current parser key. The original typo-bearing 8 rows return failure
with empty materials.
See [the material-evidence review](MATERIAL_EVIDENCE_REVIEW.md) for the regression cases,
API behavior, validation, and limits of this conservative policy.
