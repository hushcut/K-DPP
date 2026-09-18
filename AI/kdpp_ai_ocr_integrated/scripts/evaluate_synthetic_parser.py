"""Evaluate manifest ground-truth text without reading images or calling OCR.

Example (run from the AI project root)::

    python scripts/evaluate_synthetic_parser.py --manifest outputs/synthetic/synthetic_v1_pilot/manifest.csv --output parser_report.json

Use --parser-root PATH to evaluate an unchanged baseline with this same script.
Exit status is 0 for a completed evaluation (including parser mismatches), 2 for
invalid input or setup. Material comparisons never merge aliases or renormalize
ratios. Image variants are repeated text cases, not independent source labels.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import json
import re
import sys
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path


REQUIRED_FIELDS = {
    "id", "file_name", "source_group", "label_language", "selected_part",
    "original_text", "answer_materials", "answer_ratios",
    "normalized_materials", "normalized_ratios", "parts_json",
}
METRICS = (
    "parse_label_materials_exact", "parse_materials_exact",
    "selected_part_exact", "parse_label_materials_and_part_exact",
)
# Frozen answer contracts are checked independently of the generator and the
# selected --parser-root, which may be a historical checkout without this policy.
MATERIAL_POLICIES = {
    "kdpp-fiber-labels-v1": {"zh": {"spandex": "polyurethane"}},
    "kdpp-fiber-labels-v2": {},
}
_ZH_LONG_SPANDEX = re.compile(r"聚氨[酯脂][弹彈]性[纤纖][维維]")
_ZH_SPANDEX = re.compile(r"氨[纶綸](?:[丝絲])?")
_ZH_POLYURETHANE = re.compile(r"聚氨[酯脂]")


def _ratio(value, context):
    if isinstance(value, bool):
        raise ValueError(f"{context}: boolean is not a ratio")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{context}: invalid ratio {value!r}") from exc
    if not number.is_finite() or not 0 < number <= 100:
        raise ValueError(f"{context}: ratio must be finite and in (0, 100]")
    return number


def _composition(values, context, require_total=True):
    if not isinstance(values, dict) or not values:
        raise ValueError(f"{context}: expected a nonempty material-to-ratio object")
    result = {}
    for material, value in values.items():
        if not isinstance(material, str) or not material or material != material.strip():
            raise ValueError(f"{context}: invalid material key {material!r}")
        result[material] = _ratio(value, context)
    if require_total and sum(result.values()) != Decimal(100):
        raise ValueError(f"{context}: ratios must sum to exactly 100")
    return result


def _answer(row, prefix, context):
    keys = row[f"{prefix}_materials"].split(";")
    ratios = row[f"{prefix}_ratios"].split(";")
    if len(keys) != len(ratios) or len(set(keys)) != len(keys):
        raise ValueError(f"{context}: mismatched or duplicate {prefix} materials/ratios")
    return _composition(dict(zip(keys, ratios)), context)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _validate_material_markers(text, language, policy, parts, context):
    """Check Chinese elastic-fiber labels against the declared answer contract."""
    if language != "zh" or not policy:
        return
    remaining, long_count = _ZH_LONG_SPANDEX.subn("", text)
    remaining, spandex_count = _ZH_SPANDEX.subn("", remaining)
    polyurethane_count = len(_ZH_POLYURETHANE.findall(remaining))
    required = set()
    if policy == "kdpp-fiber-labels-v1":
        if long_count or spandex_count or polyurethane_count:
            required.add("polyurethane")
    else:
        if long_count or spandex_count:
            required.add("spandex")
        if polyurethane_count:
            required.add("polyurethane")
    recorded = {material for composition in parts.values() for material in composition}
    missing = required - recorded
    if missing:
        raise ValueError(
            f"{context}: original_text material markers require {sorted(required)}, "
            f"but parts_json records {sorted(recorded)}"
        )


def load_manifest(path):
    """Validate every row before evaluation and collect identical source groups."""
    groups = {}
    seen_ids, seen_files = set(), set()
    with Path(path).open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        fields = reader.fieldnames or []
        missing = REQUIRED_FIELDS - set(fields)
        if missing or len(set(fields)) != len(fields):
            raise ValueError(f"manifest: missing fields {sorted(missing)} or duplicate headers")
        for row_number, row in enumerate(reader, start=2):
            context = f"manifest row {row_number} ({row.get('id', '?')})"
            if None in row or any(row.get(field) is None for field in fields):
                raise ValueError(f"{context}: incorrect CSV column count")
            if any(not row[field].strip() for field in REQUIRED_FIELDS):
                raise ValueError(f"{context}: required field is empty")
            if row["id"] in seen_ids or row["file_name"] in seen_files:
                raise ValueError(f"{context}: duplicate id or file_name")
            seen_ids.add(row["id"])
            seen_files.add(row["file_name"])
            expected = _answer(row, "answer", context)
            if expected != _answer(row, "normalized", context):
                raise ValueError(f"{context}: normalized and original answers disagree")
            try:
                raw_parts = json.loads(row["parts_json"], object_pairs_hook=_unique_object,
                                       parse_float=Decimal)
                if not isinstance(raw_parts, dict) or not raw_parts:
                    raise ValueError("parts_json must be a nonempty object")
                parts = {part: _composition(values, f"{context} part {part}")
                         for part, values in raw_parts.items()}
            except (ValueError, TypeError) as exc:
                raise ValueError(f"{context}: invalid parts_json: {exc}") from exc
            if parts.get(row["selected_part"]) != expected:
                raise ValueError(f"{context}: selected_part composition disagrees with answer")
            policy = row.get("material_label_policy", "")
            source_parts_text = row.get("source_parts_json", "")
            source_parts = None
            if policy or source_parts_text:
                if not policy or not source_parts_text:
                    raise ValueError(f"{context}: material policy and source parts must be provided together")
                raw_source = json.loads(source_parts_text, object_pairs_hook=_unique_object,
                                        parse_float=Decimal)
                if not isinstance(raw_source, dict) or set(raw_source) != set(parts):
                    raise ValueError(f"{context}: source and displayed part names disagree")
                source_parts = {part: _composition(values, f"{context} source part {part}")
                                for part, values in raw_source.items()}
                if policy not in MATERIAL_POLICIES:
                    raise ValueError(f"{context}: unsupported material label policy {policy!r}")
                mapping = MATERIAL_POLICIES[policy].get(row["label_language"], {})
                contracted_parts = {}
                for part, composition in source_parts.items():
                    contracted = {}
                    for material, ratio in composition.items():
                        key = mapping.get(material, material)
                        contracted[key] = contracted.get(key, Decimal(0)) + ratio
                    contracted_parts[part] = contracted
                if contracted_parts != parts:
                    raise ValueError(f"{context}: source parts violate the declared material label policy")
                _validate_material_markers(
                    row["original_text"], row["label_language"], policy, parts, context
                )
            source = {
                "source_group": row["source_group"], "language": row["label_language"],
                "original_text": row["original_text"], "expected_materials": expected,
                "expected_selected_part": row["selected_part"], "parts": parts,
                "material_label_policy": policy, "source_parts": source_parts,
            }
            key = row["source_group"]
            if key not in groups:
                groups[key] = {**source, "rows": []}
            elif any(groups[key][field] != value for field, value in source.items()):
                raise ValueError(f"{context}: source_group {key!r} has inconsistent text, answer, language or parts")
            groups[key]["rows"].append({"id": row["id"], "file_name": row["file_name"]})
    if not groups:
        raise ValueError("manifest: no data rows")
    return list(groups.values())


def _predict(function, text, label=False):
    try:
        result = function(text)
        if label and not isinstance(result, dict):
            raise ValueError("parse_label returned a non-object")
        raw_materials = result.get("materials") if label else result
        materials = {} if raw_materials == {} else _composition(
            raw_materials, "parser output", require_total=False)
        return {"materials": materials,
                "selected_part": result.get("selected_part") if label else None,
                "status": result.get("status") if label else None,
                "error": None}
    except Exception as exc:
        return {"materials": {}, "selected_part": None, "status": None,
                "error": f"{type(exc).__name__}: {exc}"}


def _metrics(results, weighted):
    total = sum(item["image_rows"] if weighted else 1 for item in results)
    output = {"total": total}
    for name in METRICS:
        passed = sum((item["image_rows"] if weighted else 1)
                     for item in results if item[name])
        output[name] = {"passed": passed, "total": total,
                        "rate": passed / total if total else None}
    return output


def evaluate_manifest(manifest, parse_label, parse_materials):
    """Run pure text parsers once per validated source group."""
    groups = load_manifest(manifest)
    results = []
    for source in groups:
        text = source["original_text"]
        label = _predict(parse_label, text, label=True)
        materials = _predict(parse_materials, text)
        expected = source["expected_materials"]
        label_exact = not label["error"] and label["materials"] == expected
        part_exact = not label["error"] and label["selected_part"] == source["expected_selected_part"]
        notes = []
        if "腨纶" in text:
            notes.append({"kind": "invalid_label_spelling",
                          "message": "Generated text contains 腨纶 (U+8168); the standard acrylic spelling is 腈纶 (U+8148). Original text and answer remain unchanged."})
        if any(name in text for name in ("氨纶", "氨綸")):
            policy = source["material_label_policy"]
            if policy == "kdpp-fiber-labels-v1":
                note = {
                    "kind": "material_key_convention",
                    "message": "Historical v1 manifests use the polyurethane API key for 氨纶. Strict scores preserve that recorded answer without remapping.",
                }
            elif policy == "kdpp-fiber-labels-v2":
                note = {
                    "kind": "material_key_convention",
                    "message": "The v2 label contract maps 氨纶/氨綸 to spandex and keeps 聚氨酯 as polyurethane.",
                }
            else:
                note = {
                    "kind": "ambiguous_material_label",
                    "message": "This unversioned manifest does not declare whether 氨纶 follows the historical v1 key or the current spandex key. Strict scores preserve its recorded answer.",
                }
            notes.append(note)
        results.append({
            "source_group": source["source_group"], "language": source["language"],
            "image_rows": len(source["rows"]), "rows": source["rows"],
            "original_text": text, "expected_materials": expected,
            "expected_selected_part": source["expected_selected_part"],
            "material_label_policy": source["material_label_policy"],
            "source_parts": source["source_parts"],
            "parse_label": label, "parse_materials": materials,
            "parse_label_materials_exact": bool(label_exact),
            "parse_materials_exact": not materials["error"] and materials["materials"] == expected,
            "selected_part_exact": bool(part_exact),
            "parse_label_materials_and_part_exact": bool(label_exact and part_exact),
            "notes": notes,
        })
    languages = defaultdict(list)
    for item in results:
        languages[item["language"]].append(item)
    return {
        "schema_version": 1, "evaluation": "ground_truth_text_parser_only",
        "manifest": str(Path(manifest).resolve()),
        "manifest_sha256": hashlib.sha256(Path(manifest).read_bytes()).hexdigest(),
        "notes": [
            "No image is read and no Google Vision/OCR or Pillow call is made.",
            "Image rows are repeated text cases from source groups; they are not independent labels. Scores are not OCR or app accuracy.",
            "All manifest rows are included, regardless of include_in_accuracy; these scores are separate from real-image QA.",
            "Material keys and ratios are compared exactly, with no alias remapping, ratio tolerance, or renormalization.",
            "Known generated-label issues are annotated and remain in every denominator.",
        ],
        "summary": {"image_rows": sum(item["image_rows"] for item in results),
                    "unique_source_groups": len(results),
                    "variants_per_source_distribution": dict(sorted(Counter(item["image_rows"] for item in results).items()))},
        "metrics": {"image_rows": _metrics(results, True),
                    "unique_source_groups": _metrics(results, False)},
        "per_language": {
            language: {"image_rows": _metrics(items, True),
                       "unique_source_groups": _metrics(items, False)}
            for language, items in sorted(languages.items())},
        "source_failures": [item for item in results if not all(item[key] for key in METRICS)],
        "label_issue_sources": [item["source_group"] for item in results
                                if any(note["kind"] != "material_key_convention"
                                       for note in item["notes"])],
        "source_results": results,
    }


def _json_default(value):
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", type=Path, help="Write the JSON report here; otherwise print it")
    parser.add_argument("--parser-root", type=Path, default=Path(__file__).resolve().parents[1],
                        help="AI project directory containing apps/text/parse_label.py")
    args = parser.parse_args(argv)
    try:
        root = args.parser_root.resolve()
        module_path = root / "apps" / "text" / "parse_label.py"
        rules_path = root / "apps" / "text" / "rules.py"
        if not module_path.is_file() or not rules_path.is_file():
            raise ValueError(f"invalid parser root: {root}")
        if args.output and args.output.resolve() in {args.manifest.resolve(), module_path, rules_path}:
            raise ValueError("output must not overwrite the manifest or parser source")
        sys.path.insert(0, str(root))
        module = importlib.import_module("apps.text.parse_label")
        if Path(module.__file__).resolve() != module_path:
            raise ValueError("loaded parser does not match --parser-root; run the CLI in a fresh process")
        report = evaluate_manifest(args.manifest, module.parse_label, module.parse_materials)
        report["parser"] = {"root": str(root), "files_sha256": {
            str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (module_path, rules_path)}}
        encoded = json.dumps(report, ensure_ascii=False, indent=2, default=_json_default) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded, encoding="utf-8")
            print(f"Report: {args.output.resolve()}")
        else:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8")
            print(encoded, end="")
        return 0
    except (OSError, ValueError, csv.Error, ImportError) as exc:
        print(f"Evaluation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
