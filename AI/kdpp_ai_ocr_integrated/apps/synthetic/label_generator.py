from __future__ import annotations

import csv
import hashlib
import json
import random
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[2]

MATERIAL_NAMES = {
    "cotton": {"en": "COTTON", "ko": "\uba74", "ja": "\u7dbf", "zh": "\u68c9"},
    "polyester": {"en": "POLYESTER", "ko": "\ud3f4\ub9ac\uc5d0\uc2a4\ud130", "ja": "\u30dd\u30ea\u30a8\u30b9\u30c6\u30eb", "zh": "\u805a\u916f\u7ea4\u7ef4"},
    "nylon": {"en": "NYLON", "ko": "\ub098\uc77c\ub860", "ja": "\u30ca\u30a4\u30ed\u30f3", "zh": "\u9526\u7eb6"},
    "polyurethane": {"en": "POLYURETHANE", "ko": "\ud3f4\ub9ac\uc6b0\ub808\ud0c4", "ja": "\u30dd\u30ea\u30a6\u30ec\u30bf\u30f3", "zh": "\u6c28\u7eb6"},
    "spandex": {"en": "SPANDEX", "ko": "\uc2a4\ud310\ub371\uc2a4", "ja": "\u30b9\u30d1\u30f3\u30c7\u30c3\u30af\u30b9", "zh": "\u6c28\u7eb6"},
    "wool": {"en": "WOOL", "ko": "\ubaa8", "ja": "\u7f8a\u6bdb", "zh": "\u7f8a\u6bdb"},
    "linen": {"en": "LINEN", "ko": "\ub9b0\ub128", "ja": "\u9ebb", "zh": "\u4e9a\u9ebb"},
    "rayon": {"en": "RAYON", "ko": "\ub808\uc774\uc628", "ja": "\u30ec\u30fc\u30e8\u30f3", "zh": "\u4eba\u9020\u4e1d"},
    "viscose": {"en": "VISCOSE", "ko": "\ube44\uc2a4\ucf54\uc2a4", "ja": "\u30d3\u30b9\u30b3\u30fc\u30b9", "zh": "\u7c98\u80f6\u7ea4\u7ef4"},
    "acrylic": {"en": "ACRYLIC", "ko": "\uc544\ud06c\ub9b4", "ja": "\u30a2\u30af\u30ea\u30eb", "zh": "\u8148\u7eb6"},
    "silk": {"en": "SILK", "ko": "\uc2e4\ud06c", "ja": "\u7d79", "zh": "\u8695\u4e1d"},
    "cashmere": {"en": "CASHMERE", "ko": "\uce90\uc2dc\ubbf8\uc5b4", "ja": "\u30ab\u30b7\u30df\u30e4", "zh": "\u7f8a\u7ed2"},
    "modal": {"en": "MODAL", "ko": "\ubaa8\ub2ec", "ja": "\u30e2\u30c0\u30fc\u30eb", "zh": "\u83ab\u4ee3\u5c14"},
    "lyocell": {"en": "LYOCELL", "ko": "\ub9ac\uc624\uc140", "ja": "\u30ea\u30e8\u30bb\u30eb", "zh": "\u83b1\u8d5b\u5c14"},
}

HEADINGS = {
    "en": "FIBER CONTENT",
    "ko": "\uc12c\uc720 \ud63c\uc6a9\ub960",
    "ja": "\u7d44\u6210\u8868\u793a",
    "zh": "\u7ea4\u7ef4\u6210\u5206",
}

PART_NAMES = {
    "outer": {"en": "SHELL", "ko": "\uac89\uac10", "ja": "\u8868\u5730", "zh": "\u9762\u6599"},
    "lining": {"en": "LINING", "ko": "\uc548\uac10", "ja": "\u88cf\u5730", "zh": "\u91cc\u6599"},
    "rib": {"en": "RIB", "ko": "\ub9ac\ube0c", "ja": "\u30ea\u30d6", "zh": "\u87ba\u7eb9"},
}

FOOTERS = {
    "en": "MADE IN KOREA",
    "ko": "\ud55c\uad6d\uc81c\uc870",
    "ja": "\u97d3\u56fd\u88fd",
    "zh": "\u97e9\u56fd\u5236\u9020",
}

RATIO_PATTERNS = {
    1: [(100,)],
    2: [(95, 5), (90, 10), (85, 15), (80, 20), (72, 28), (70, 30), (65, 35), (60, 40), (50, 50)],
    3: [(80, 15, 5), (70, 25, 5), (60, 35, 5), (55, 40, 5), (50, 30, 20), (48, 48, 4)],
}

THEMES = {
    "white": {"label": (247, 247, 243), "text": (25, 25, 25), "border": (175, 175, 170)},
    "ivory": {"label": (237, 229, 207), "text": (38, 34, 28), "border": (159, 148, 125)},
    "black": {"label": (31, 31, 33), "text": (231, 231, 226), "border": (105, 105, 108)},
}

MANIFEST_FIELDS = [
    "id",
    "file_name",
    "answer_materials",
    "answer_ratios",
    "case_type",
    "include_in_accuracy",
    "normalized_materials",
    "normalized_ratios",
    "shooting_pose",
    "lighting",
    "resolution",
    "label_language",
    "label_condition",
    "notation_type",
    "memo",
    "source_group",
    "split",
    "selected_part",
    "original_text",
    "parts_json",
    "transform_json",
    "image_sha256",
    "generator_version",
    "seed",
]


@dataclass(frozen=True)
class LabelSpec:
    source_group: str
    language: str
    layout: str
    theme: str
    parts: dict[str, dict[str, int]]

    @property
    def selected_part(self) -> str:
        return "outer" if "outer" in self.parts else "generic"

    @property
    def answer(self) -> dict[str, int]:
        return self.parts[self.selected_part]


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as stream:
        config = json.load(stream)
    _validate_config(config)
    return config


def _validate_config(config: dict[str, Any]) -> None:
    required = {
        "dataset_name",
        "generator_version",
        "seed",
        "base_label_count",
        "variants_per_label",
        "image_width",
        "image_height",
        "languages",
        "layouts",
        "conditions",
        "themes",
        "materials",
        "output_dir",
    }
    missing = sorted(required - set(config))
    if missing:
        raise ValueError("Missing config keys: " + ", ".join(missing))

    if int(config["base_label_count"]) < 1 or int(config["variants_per_label"]) < 1:
        raise ValueError("base_label_count and variants_per_label must be positive")
    if not config["languages"] or not set(config["languages"]).issubset(HEADINGS):
        raise ValueError("languages must contain supported language codes")
    if not config["layouts"] or not set(config["layouts"]).issubset(
        {"material_first", "ratio_first", "stacked_columns"}
    ):
        raise ValueError("layouts contains an unsupported layout")
    if not config["conditions"]:
        raise ValueError("conditions must not be empty")
    if not config["themes"] or not set(config["themes"]).issubset(THEMES):
        raise ValueError("themes contains an unsupported theme")
    if not config["materials"] or not set(config["materials"]).issubset(MATERIAL_NAMES):
        raise ValueError("materials contains an unsupported material key")


def _font_candidates(language: str) -> list[Path]:
    windows = Path("C:/Windows/Fonts")
    shared = [
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"),
    ]
    by_language = {
        "ko": [windows / "malgun.ttf", windows / "malgunbd.ttf"],
        "ja": [windows / "YuGothM.ttc", windows / "msgothic.ttc"],
        "zh": [windows / "msyh.ttc", windows / "msjh.ttc", windows / "simsun.ttc"],
        "en": [windows / "arial.ttf", windows / "calibri.ttf"],
    }
    return by_language.get(language, []) + shared


def _load_font(language: str, size: int, override: str = "") -> tuple[ImageFont.FreeTypeFont | ImageFont.ImageFont, str]:
    candidates = [Path(override)] if override else []
    candidates.extend(_font_candidates(language))
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size), str(candidate)
    if language != "en":
        raise FileNotFoundError(f"No font capable of rendering language '{language}' was found")
    return ImageFont.load_default(), "Pillow-default"


def _choose_composition(rng: random.Random, materials: list[str], count: int | None = None) -> dict[str, int]:
    material_count = count or rng.choices([1, 2, 3], weights=[3, 6, 2], k=1)[0]
    material_count = min(material_count, len(materials))
    ratios = rng.choice(RATIO_PATTERNS[material_count])

    main_candidates = [key for key in materials if key not in {"spandex", "polyurethane"}]
    first = rng.choice(main_candidates or materials)
    remaining = [key for key in materials if key != first]
    selected = [first] + rng.sample(remaining, material_count - 1)

    # Elastic fibers are more plausible as the smallest component.
    if material_count > 1:
        elastic = [key for key in selected if key in {"spandex", "polyurethane"}]
        if elastic:
            selected = [key for key in selected if key not in elastic] + elastic

    return dict(zip(selected, ratios))


def _make_spec(index: int, config: dict[str, Any], rng: random.Random) -> LabelSpec:
    languages = list(config["languages"])
    layouts = list(config["layouts"])
    themes = list(config["themes"])
    materials = list(config["materials"])

    language = languages[index % len(languages)]
    layout = layouts[(index // len(languages)) % len(layouts)]
    theme = themes[(index // max(1, len(layouts))) % len(themes)]
    part_probability = float(config.get("part_label_probability", 0.35))

    if rng.random() < part_probability:
        outer = _choose_composition(rng, materials)
        excluded = set(outer)
        lining_candidates = [key for key in materials if key not in excluded and key not in {"spandex", "polyurethane"}]
        lining_key = rng.choice(lining_candidates or materials)
        parts: dict[str, dict[str, int]] = {"outer": outer, "lining": {lining_key: 100}}
        if rng.random() < 0.25:
            rib_candidates = [key for key in materials if key not in {"spandex", "polyurethane"}]
            rib_main = rng.choice(rib_candidates)
            elastic_candidates = [key for key in materials if key in {"spandex", "polyurethane"}]
            if elastic_candidates:
                parts["rib"] = {rib_main: 95, rng.choice(elastic_candidates): 5}
    else:
        parts = {"generic": _choose_composition(rng, materials)}

    return LabelSpec(
        source_group=f"SYN_SOURCE_{index + 1:04d}",
        language=language,
        layout=layout,
        theme=theme,
        parts=parts,
    )


def _material_lines(composition: dict[str, int], language: str, layout: str) -> list[str]:
    pairs = [(MATERIAL_NAMES[key][language], ratio) for key, ratio in composition.items()]
    if layout == "ratio_first":
        return [f"{ratio}%  {name}" for name, ratio in pairs]
    if layout == "stacked_columns" and len(pairs) > 1:
        return [name for name, _ in pairs] + [f"{ratio}%" for _, ratio in pairs]
    return [f"{name}  {ratio}%" for name, ratio in pairs]


def _label_lines(spec: LabelSpec) -> list[str]:
    lines = [HEADINGS[spec.language]]
    for part, composition in spec.parts.items():
        if part != "generic":
            lines.append(PART_NAMES[part][spec.language])
        lines.extend(_material_lines(composition, spec.language, spec.layout))
    lines.extend(["", FOOTERS[spec.language]])
    return lines


def _fit_font(
    lines: list[str], language: str, max_width: int, max_height: int, override: str
) -> tuple[ImageFont.FreeTypeFont | ImageFont.ImageFont, str, int]:
    probe = Image.new("RGB", (max_width, max_height), "white")
    draw = ImageDraw.Draw(probe)
    for size in range(38, 17, -2):
        font, font_path = _load_font(language, size, override)
        widths = [draw.textbbox((0, 0), line or " ", font=font)[2] for line in lines]
        line_height = draw.textbbox((0, 0), "Ag\uac00", font=font)[3] + 8
        if max(widths, default=0) <= max_width and line_height * len(lines) <= max_height:
            return font, font_path, line_height
    font, font_path = _load_font(language, 16, override)
    return font, font_path, 24


def _render_label(spec: LabelSpec, config: dict[str, Any], rng: random.Random) -> tuple[Image.Image, str, str]:
    width = rng.randint(610, 730)
    height = rng.randint(450, 560)
    palette = THEMES[spec.theme]
    label = Image.new("RGBA", (width, height), (*palette["label"], 255))
    draw = ImageDraw.Draw(label)

    draw.rectangle((8, 8, width - 9, height - 9), outline=(*palette["border"], 255), width=2)
    for y in range(12, height - 12, 12):
        draw.point((12, y), fill=(*palette["border"], 170))
        draw.point((width - 13, y), fill=(*palette["border"], 170))

    lines = _label_lines(spec)
    font, font_path, line_height = _fit_font(
        lines,
        spec.language,
        width - 90,
        height - 90,
        str(config.get("font_path", "")),
    )
    total_height = line_height * len(lines)
    y = max(35, (height - total_height) // 2)
    text_color = (*palette["text"], 255)
    for line_number, line in enumerate(lines):
        if not line:
            y += line_height
            continue
        bbox = draw.textbbox((0, 0), line, font=font)
        x = max(35, (width - (bbox[2] - bbox[0])) // 2)
        draw.text((x, y), line, font=font, fill=text_color)
        if line_number == 0:
            underline_y = y + line_height - 3
            draw.line((x, underline_y, width - x, underline_y), fill=(*palette["border"], 220), width=1)
        y += line_height

    return label, font_path, "\n".join(lines)


def _add_glare(image: Image.Image, rng: random.Random) -> Image.Image:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    width, height = image.size
    stripe = rng.randint(90, 170)
    x = rng.randint(width // 5, width * 3 // 5)
    draw.polygon(
        [(x, 0), (x + stripe, 0), (x + stripe + height // 3, height), (x + height // 3, height)],
        fill=(255, 255, 245, rng.randint(55, 100)),
    )
    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=24))
    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


def _apply_condition(
    canvas: Image.Image, label: Image.Image, condition: str, rng: random.Random
) -> tuple[Image.Image, dict[str, Any]]:
    transforms: dict[str, Any] = {"condition": condition}

    angle = 0.0
    if condition in {"rotated", "mixed"}:
        angle = round(rng.uniform(-15.0, 15.0), 2)
        label = label.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
    transforms["rotation_degrees"] = angle

    shear = 0.0
    if condition in {"perspective", "mixed"}:
        shear = round(rng.uniform(-0.13, 0.13), 3)
        label = label.transform(
            label.size,
            Image.Transform.AFFINE,
            (1, shear, -shear * label.height / 2, 0, 1, 0),
            resample=Image.Resampling.BICUBIC,
        )
    transforms["affine_shear"] = shear

    max_x = max(0, canvas.width - label.width)
    max_y = max(0, canvas.height - label.height)
    x = max_x // 2 + rng.randint(-min(35, max_x // 2), min(35, max_x // 2))
    y = max_y // 2 + rng.randint(-min(25, max_y // 2), min(25, max_y // 2))
    canvas.paste(label, (x, y), label)

    result = canvas.convert("RGB")
    if condition in {"low_light", "mixed"}:
        brightness = round(rng.uniform(0.48, 0.7), 2)
        result = ImageEnhance.Brightness(result).enhance(brightness)
        result = ImageEnhance.Contrast(result).enhance(rng.uniform(0.8, 1.15))
        transforms["brightness"] = brightness
    else:
        transforms["brightness"] = 1.0

    blur_radius = 0.0
    if condition in {"blur", "mixed"}:
        blur_radius = round(rng.uniform(1.1, 2.2), 2)
        result = result.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    transforms["blur_radius"] = blur_radius

    if condition in {"glare", "mixed"}:
        result = _add_glare(result, rng)
        transforms["glare"] = True
    else:
        transforms["glare"] = False

    if condition != "clean":
        noise = Image.frombytes("L", result.size, rng.randbytes(result.width * result.height)).convert("RGB")
        noise_alpha = round(rng.uniform(0.015, 0.035), 3)
        result = Image.blend(result, noise, alpha=noise_alpha)
        transforms["noise_alpha"] = noise_alpha
    else:
        transforms["noise_alpha"] = 0.0

    return result, transforms


def _make_canvas(config: dict[str, Any], rng: random.Random) -> Image.Image:
    width = int(config["image_width"])
    height = int(config["image_height"])
    garment_colors = [(29, 31, 35), (57, 62, 67), (80, 72, 62), (31, 48, 54), (104, 98, 91)]
    base = rng.choice(garment_colors)
    canvas = Image.new("RGB", (width, height), base)
    draw = ImageDraw.Draw(canvas)
    for offset in range(-height, width, 18):
        shade = tuple(min(255, channel + rng.randint(3, 12)) for channel in base)
        draw.line((offset, 0, offset + height, height), fill=shade, width=1)
    return canvas


def _save_contact_sheet(rows: list[dict[str, str]], images_dir: Path, output_path: Path, limit: int) -> None:
    selected = rows[: max(1, limit)]
    columns = 4
    cell_width, cell_height = 240, 210
    rows_count = (len(selected) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell_width, rows_count * cell_height), (245, 245, 245))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()

    for index, row in enumerate(selected):
        with Image.open(images_dir / row["file_name"]) as source:
            preview = source.convert("RGB")
            preview.thumbnail((cell_width - 12, cell_height - 36), Image.Resampling.LANCZOS)
        left = (index % columns) * cell_width + (cell_width - preview.width) // 2
        top = (index // columns) * cell_height + 5
        sheet.paste(preview, (left, top))
        caption = f'{row["id"]} {row["label_language"]}/{row["label_condition"]}'
        draw.text(((index % columns) * cell_width + 8, top + preview.height + 7), caption, font=font, fill=(20, 20, 20))

    sheet.save(output_path, format="JPEG", quality=92, optimize=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _prepare_output(output_dir: Path) -> Path:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir = output_dir / "images"
    images_dir.mkdir(exist_ok=True)
    return images_dir


def generate_dataset(config: dict[str, Any], output_dir: str | Path | None = None) -> dict[str, Any]:
    _validate_config(config)
    resolved_output = Path(output_dir) if output_dir else Path(str(config["output_dir"]))
    if not resolved_output.is_absolute():
        resolved_output = PROJECT_ROOT / resolved_output
    resolved_output = resolved_output.resolve()
    images_dir = _prepare_output(resolved_output)

    seed = int(config["seed"])
    spec_rng = random.Random(seed)
    specs = [_make_spec(index, config, spec_rng) for index in range(int(config["base_label_count"]))]

    rows: list[dict[str, str]] = []
    conditions = list(config["conditions"])
    quality_min = int(config.get("jpeg_quality_min", 75))
    quality_max = int(config.get("jpeg_quality_max", 95))
    variants = int(config["variants_per_label"])
    serial = 1

    for source_index, spec in enumerate(specs):
        for variant_index in range(variants):
            sample_seed = seed + source_index * 10_000 + variant_index
            rng = random.Random(sample_seed)
            condition = conditions[(source_index * variants + variant_index) % len(conditions)]
            canvas = _make_canvas(config, rng)
            label, font_path, original_text = _render_label(spec, config, rng)
            image, transforms = _apply_condition(canvas, label, condition, rng)

            sample_id = f"SYN{serial:05d}"
            file_name = f"{sample_id}.jpg"
            image_path = images_dir / file_name
            jpeg_quality = rng.randint(quality_min, quality_max)
            image.save(image_path, format="JPEG", quality=jpeg_quality, optimize=True)
            transforms["jpeg_quality"] = jpeg_quality

            answer_keys = list(spec.answer)
            answer_values = [spec.answer[key] for key in answer_keys]
            row = {
                "id": sample_id,
                "file_name": file_name,
                "answer_materials": ";".join(answer_keys),
                "answer_ratios": ";".join(str(value) for value in answer_values),
                "case_type": "synthetic_material_label",
                "include_in_accuracy": "false",
                "normalized_materials": ";".join(answer_keys),
                "normalized_ratios": ";".join(str(value) for value in answer_values),
                "shooting_pose": "synthetic",
                "lighting": "low_light" if condition in {"low_light", "mixed"} else "synthetic_light",
                "resolution": f'{config["image_width"]}x{config["image_height"]}',
                "label_language": spec.language,
                "label_condition": condition,
                "notation_type": spec.layout,
                "memo": f"generated; font={Path(font_path).name}",
                "source_group": spec.source_group,
                "split": "unassigned",
                "selected_part": spec.selected_part,
                "original_text": original_text,
                "parts_json": json.dumps(spec.parts, ensure_ascii=False, sort_keys=True),
                "transform_json": json.dumps(transforms, ensure_ascii=False, sort_keys=True),
                "image_sha256": _sha256(image_path),
                "generator_version": str(config["generator_version"]),
                "seed": str(sample_seed),
            }
            rows.append(row)
            serial += 1

    manifest_path = resolved_output / "manifest.csv"
    with manifest_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    resolved_config = dict(config)
    resolved_config["output_dir"] = str(resolved_output)
    with (resolved_output / "config_resolved.json").open("w", encoding="utf-8") as stream:
        json.dump(resolved_config, stream, ensure_ascii=False, indent=2)

    summary = {
        "dataset_name": config["dataset_name"],
        "generator_version": config["generator_version"],
        "seed": seed,
        "base_labels": len(specs),
        "variants_per_label": variants,
        "images": len(rows),
        "unique_source_groups": len({row["source_group"] for row in rows}),
        "unique_image_hashes": len({row["image_sha256"] for row in rows}),
        "languages": dict(Counter(row["label_language"] for row in rows)),
        "conditions": dict(Counter(row["label_condition"] for row in rows)),
        "layouts": dict(Counter(row["notation_type"] for row in rows)),
        "output_dir": str(resolved_output),
    }
    with (resolved_output / "summary.json").open("w", encoding="utf-8") as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=2)

    _save_contact_sheet(
        rows,
        images_dir,
        resolved_output / "contact_sheet.jpg",
        int(config.get("contact_sheet_limit", 24)),
    )
    return summary
