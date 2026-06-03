# K-DPP AI OCR Integrated

This is a standalone AI-part draft that keeps the modular `kyh/ai-ocr` direction and folds in the useful preprocessing ideas from `feat/ai-ocr`.

It does not modify the original `C:\KDPP\K-DPP` project.

## Goals

- Keep symbol recognition and text OCR/parsing separate.
- Reuse the richer material alias idea from `feat/ai-ocr`.
- Fix the parser/result shape mismatch.
- Add a more reliable training loop for overfitting checks.
- Save experiment models separately from the current model.
- Provide evaluation output beyond a single accuracy number.

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
      rules.py
  scripts/
    check_split_leakage.py
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

## Train

```bash
python -m apps.symbol.train_symbol_experiment
```

The experiment model is saved to:

```text
models/symbol/best_symbol_model_exp.pt
```

## Evaluate

```bash
python -m apps.symbol.evaluate_symbol --model models/symbol/best_symbol_model_exp.pt --split valid
```

Outputs include overall accuracy, class accuracy, confusion matrix CSV, and wrong predictions CSV.

## Combined Batch

Requires Google Vision credentials:

```bash
python scripts/run_combined_batch.py --split valid --credentials key.json
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
python scripts/run_qa_batch.py --image-dir "C:\Users\hany0\OneDrive\?? ??\kdpp-dataset" --answer-key "C:\K-DPP QA\K-DPP\QA\answer_key_template.csv" --credentials key.json
```

Output:

```text
outputs/qa_batch_results.csv
```
