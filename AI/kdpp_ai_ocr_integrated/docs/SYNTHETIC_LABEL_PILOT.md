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
local OCR experiments. The 163 real QA images must remain the final real-photo holdout set.

## Generate

Run from `AI/kdpp_ai_ocr_integrated`:

```powershell
python scripts/generate_synthetic_labels.py
```

The default output is `outputs/synthetic/synthetic_v1_pilot`. Generated output is ignored by Git.
The generator refuses to overwrite a non-empty output directory. Use `--output` for another run:

```powershell
python scripts/generate_synthetic_labels.py --output outputs/synthetic/synthetic_v1_pilot_run2
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

## Validation before scaling

1. Inspect `contact_sheet.jpg` and a sample from every language and condition.
2. Confirm each expected composition in `manifest.csv` matches the visible label.
3. Run OCR and parser experiments separately, reporting OCR failure and parsing failure.
4. Keep the real-photo QA score separate from the synthetic-data score.
5. Scale only after the 80-image pilot passes these checks.
