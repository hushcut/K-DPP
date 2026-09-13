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

The current default is `outputs/synthetic/synthetic_v1_pilot_corrected_v1_0_2` (generator v1.0.2).
The original v1.0.0 pilot stays in `outputs/synthetic/synthetic_v1_pilot`, with its own resolved config.
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

Generator v1.0.2 records `source_parts_json` before its label-key policy is applied, and
`parts_json` after it. The versioned `material_label_policy` is `kdpp-fiber-labels-v1`.
On Chinese fiber labels, the existing API key for `氨纶` is `polyurethane`, so the generator
resolves a sampled `spandex` key to that display/answer key before rendering. Collisions merge
within each part; other languages keep both keys. This is a local API compatibility rule, not
a universal equivalence between spandex and polyurethane. The parser and backend are unchanged.

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
the acrylic spelling to `腈纶` for future runs. Existing images and answers are
preserved. Generator v1.0.2 additionally records and applies the label-key contract before
rendering. The corrected pilot matches 80/80 image rows (20/20 distinct texts), while the
unchanged original remains 72/80 with the same parser. This is a dataset correction, not an
additional parser-performance gain. Image OCR has not been evaluated yet.

See [the parser review](PARSER_ALIAS_REVIEW.md) for results, limitations, and next steps.
See [the pilot correction review](PILOT_CORRECTION_REVIEW.md) for the contract, exact changes,
preservation checks, and reproduction commands.

## Subsequent material-evidence validation

The parser now requires explicit material/ratio correspondence and a complete 100% composition.
It preserves decimal ratios, rejects missing or contradictory evidence, and keeps a failed outer
part from being replaced with a valid lining. The corrected pilot remains 80/80; its images and
answers are unchanged. The original typo-bearing 8 rows now return failure with empty materials.
See [the material-evidence review](MATERIAL_EVIDENCE_REVIEW.md) for the regression cases,
API behavior, validation, and limits of this conservative policy.
