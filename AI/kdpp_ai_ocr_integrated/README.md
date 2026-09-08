# K-DPP AI OCR Integrated

This is the AI module for the `kyh/ai` branch, based on
`ksw/ai-ocr-enhancement`. Text OCR/parsing and care-symbol classification
remain separate because they use different input assumptions and evaluation
criteria.

## Goals

- Keep symbol recognition and text OCR/parsing separate.
- Reuse the richer material alias idea from `feat/ai-ocr`.
- Fix the parser/result shape mismatch.
- Add a more reliable training loop for overfitting checks.
- Save experiment models separately from the current model.
- Provide evaluation output beyond a single accuracy number.
- Keep the current DPP flow limited to OCR material analysis; symbol classification remains experimental.

## Suggested Layout

```text
kdpp_ai_ocr_integrated/
  apps/
    symbol/
      class_map.py
      dataset_csv.py
      evaluate_symbol.py
      predict_symbol.py
      train_symbol_experiment.py
    text/
      ocr_text.py
      parse_label.py
      qa_dataset.py
      rules.py
  scripts/
    audit_ocr_qa_dataset.py
    audit_symbol_dataset.py
    check_split_leakage.py
    run_ai_checks.py
    run_combined_batch.py
  data/
    train/
    valid/
    test/
  models/
    symbol/
  outputs/
```

## Data

Copy your Roboflow-style folders into:

```text
data/train
data/valid
data/test
```

Each split should contain `_classes.csv` and the referenced image files.

### Dataset contract before training

`_classes.csv` must have a `filename` column followed by binary `0`/`1` class
columns in exactly the same order for every split. A row may have multiple
positive class columns, so the current symbol model is multi-label. A row with
all zeros is retained as a valid negative example.

Use group-aware splitting: keep an original image and all of its augmented or
near-duplicate derivatives in the same split. The project does not silently
create a split because the correct ratio depends on the available groups.
For a new dataset, start with approximately 70% train, 15% validation, and
15% test by source-image group; document any justified deviation.

Before training, run the read-only dataset audit:

```bash
python -m scripts.audit_symbol_dataset --data-dir data
```

The audit reports split ratios, per-class positive counts, all-negative rows,
the number of multi-positive rows, and whether the CSV is structurally
multi-label. It also blocks source-name and byte-identical leakage across
splits. Training additionally rejects a declared class with no positive train
sample, since that class cannot be learned.

Do not use test data to select thresholds, augmentation settings, or model
architecture. Those decisions use validation data; test data is used once for
the final report.

## Train

```bash
python -m apps.symbol.train_symbol_experiment
```

The training command runs split-leakage and train-class-coverage checks before
loading the model. Its headline validation metrics are macro-F1, micro-F1, and
exact match; Hamming accuracy is diagnostic only because sparse multi-label
data can make it look artificially high.

The experiment model is saved to:

```text
models/symbol/best_symbol_model_exp.pt
```

## Evaluate

```bash
python -m apps.symbol.evaluate_symbol --model models/symbol/best_symbol_model_exp.pt --split valid
```

Outputs include overall accuracy, class accuracy, confusion matrix CSV, and wrong predictions CSV.

## Current service scope

The DPP integration currently uses only material OCR and parsing:

```text
label image -> Google Vision OCR -> material/ratio parser -> material result
```

`apps/symbol/` is a separate ResNet18 experiment for an **already-cropped**
care symbol. It does not detect symbols in a full label image and is not part
of the current DPP material/carbon calculation path. Its dataset, split, and
model-comparison results must therefore be reported separately.

## OCR QA data contract

The OCR QA answer CSV requires these columns:

```text
file_name, answer_materials, answer_ratios
```

Use canonical material keys such as `cotton`, `polyester`, `spandex`, and
`polyurethane`. `answer_materials` may be `cotton;polyester` with matching
`answer_ratios` (`80;20`), or a self-contained form such as
`cotton:80;polyester:20`.

For an analysis that can explain failures by capture condition, add these
recommended columns to every QA row:

```text
split, source_group, capture_condition, label_layout
```

- `split`: `train`, `valid`, or `test` when QA cases are used for rule tuning.
- `source_group`: one original image and all derived/near-duplicate images
  share a group, so the audit can detect cross-split leakage.
- `capture_condition`: for example `indoor`, `night`, `reflection`, `blur`,
  or `wrinkle`.
- `label_layout`: for example `same_line`, `alternating_lines`, `stacked`, or
  `multi_part`.

Run this command before changing parsing rules. It only reads the dataset and
never calls Google Vision:

```bash
python -m scripts.audit_ocr_qa_dataset \
  --image-dir "C:\K-DPP-QA-DATASET\images" \
  --answer-key "C:\K-DPP-QA-DATASET\answer_key.csv" \
  --strict
```

The report shows material coverage, label cardinality, capture-condition
coverage, missing metadata, unmatched images/answers, and `source_group`
leakage. It does not claim that the dataset is sufficient; that judgment must
be made from the resulting counts and the intended deployment conditions.
## Combined Batch

Requires Google Vision credentials:

```bash
python -m scripts.run_combined_batch --split valid --credentials key.json
```



## Accuracy Improvement Version

This copy adds a more robust material parser for real QA images.

### What changed

- Parses material composition by line instead of only adjacent tokens.
- Detects garment sections such as outer fabric, lining, filling, rib, sleeve, and pocket.
- Uses outer/generic material as the representative `materials` result while preserving detailed `parts`.
- Avoids blindly normalizing unrelated sections into one 100% total.
- Adds Japanese/Chinese/Korean material aliases and common OCR corrections.
- Adds a QA batch script for comparing OCR results against an answer key CSV.

### Expected response shape

```json
{
  "status": "success",
  "materials": {
    "cotton": 80,
    "polyester": 20
  },
  "materials_korean": "? 80%, ????? 20%",
  "raw_ocr_preview": "COTTON 80% POLYESTER 20%",
  "confidence": {
    "ocr": "high"
  },
  "selected_part": "outer",
  "parts": {
    "outer": {
      "cotton": 80,
      "polyester": 20
    }
  }
}
```

### QA batch test

```bash
python -m scripts.run_qa_batch --image-dir "C:\K-DPP-QA-DATASET\images" --answer-key "C:\K-DPP-QA-DATASET\answer_key.csv" --credentials "C:\secure\vision-key.json"
```

Output:

```text
outputs/qa_batch_results.csv
outputs/qa_batch_results.summary.json
outputs/qa_ocr_cache.json
```

The first run stores every raw Vision response that was actually requested
(original and, when needed, preprocessed candidates). Later parser and
candidate-selection changes can be evaluated without another Vision request:

```bash
python -m scripts.run_qa_batch --image-dir "C:\K-DPP-QA-DATASET\images" --answer-key "C:\K-DPP-QA-DATASET\answer_key.csv" --offline
```

Use `--refresh-ocr-cache` only when OCR preprocessing itself changes and a new
Vision result is intentionally required. The cache can contain label text, is
stored under the ignored `outputs/` directory, and must not be committed.
