"""Generate deterministic, labeled care-label images without calling OCR services."""

from __future__ import annotations

import csv
import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont


MATERIAL_NAMES = {
    "en": {
        "cotton": "Cotton",
        "polyester": "Polyester",
        "rayon": "Rayon",
        "nylon": "Nylon",
        "acrylic": "Acrylic",
        "wool": "Wool",
        "cashmere": "Cashmere",
        "lyocell": "Lyocell",
        "modal": "Modal",
        "spandex": "Spandex",
        "polyurethane": "Polyurethane",
    },
    "ko": {
        "cotton": "면",
        "polyester": "폴리에스터",
        "rayon": "레이온",
        "nylon": "나일론",
        "acrylic": "아크릴",
        "wool": "모",
        "cashmere": "캐시미어",
        "lyocell": "리오셀",
        "modal": "모달",
        "spandex": "스판덱스",
        "polyurethane": "폴리우레탄",
    },
    "ja": {
        "cotton": "綿",
        "polyester": "ポリエステル",
        "rayon": "レーヨン",
        "nylon": "ナイロン",
        "acrylic": "アクリル",
        "wool": "毛",
        "cashmere": "カシミヤ",
        "lyocell": "リヨセル",
        "modal": "モダール",
        "spandex": "スパンデックス",
        "polyurethane": "ポリウレタン",
    },
    "zh": {
        "cotton": "棉",
        "polyester": "聚酯纤维",
        "rayon": "人造丝",
        "nylon": "锦纶",
        "acrylic": "腈纶",
        "wool": "羊毛",
        "cashmere": "羊绒",
        "lyocell": "莱赛尔",
        "modal": "莫代尔",
        "spandex": "氨纶",
        "polyurethane": "聚氨酯",
    },
}

PART_NAMES = {
    "en": {"outer": "Shell", "lining": "Lining"},
    "ko": {"outer": "겉감", "lining": "안감"},
    "ja": {"outer": "表地", "lining": "裏地"},
    "zh": {"outer": "面料", "lining": "里料"},
}

NOTO_CJK_FONT_CANDIDATES = [
    "NotoSansCJK-Regular.ttc",
    "NotoSansCJKkr-Regular.otf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]

FONT_CANDIDATES = {
    "en": ["arial.ttf", "DejaVuSans.ttf"],
    "ko": [
        "malgun.ttf",
        "C:/Windows/Fonts/malgun.ttf",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        *NOTO_CJK_FONT_CANDIDATES,
    ],
    "ja": [
        "msgothic.ttc",
        "C:/Windows/Fonts/msgothic.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
        *NOTO_CJK_FONT_CANDIDATES,
    ],
    "zh": [
        "msyh.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        *NOTO_CJK_FONT_CANDIDATES,
    ],
}

SUPPORTED_LAYOUTS = {"material_first", "ratio_first", "stacked_columns"}
THEME_STYLES = {
    "white": {"background": (255, 255, 255), "foreground": (0, 0, 0)},
    "ivory": {"background": (255, 253, 240), "foreground": (42, 35, 28)},
    "black": {"background": (25, 25, 25), "foreground": (245, 245, 245)},
}
SUPPORTED_CONDITIONS = {
    "clean",
    "rotation",
    "blur",
    "glare",
    "low_light",
    "perspective",
    "mixed",
}


@dataclass(frozen=True)
class LabelSpec:
    source_group: str
    language: str
    parts: dict[str, dict[str, int]]
    layout: str
    theme: str


def load_config(path: str | Path) -> dict[str, Any]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_config(config)
    return config


def validate_config(config: dict[str, Any]) -> None:
    required = {
        "version",
        "seed",
        "base_label_count",
        "variants_per_label",
        "languages",
        "conditions",
        "layouts",
        "themes",
        "materials",
        "image_width",
        "image_height",
        "jpeg_quality_min",
        "jpeg_quality_max",
    }
    missing = sorted(required - set(config))
    if missing:
        raise ValueError(f"Synthetic config is missing: {', '.join(missing)}")
    if int(config["base_label_count"]) < 1 or int(config["variants_per_label"]) < 1:
        raise ValueError("base_label_count and variants_per_label must be positive")
    for language in config["languages"]:
        if language not in MATERIAL_NAMES:
            raise ValueError(f"Unsupported synthetic label language: {language}")
    unknown_materials = sorted(set(config["materials"]) - set(MATERIAL_NAMES["en"]))
    if unknown_materials:
        raise ValueError(f"Unsupported synthetic materials: {', '.join(unknown_materials)}")
    if not config["conditions"]:
        raise ValueError("conditions must not be empty")
    unknown_conditions = sorted(set(config["conditions"]) - SUPPORTED_CONDITIONS)
    if unknown_conditions:
        raise ValueError(
            "Unsupported synthetic image conditions: " + ", ".join(unknown_conditions)
        )
    if not config["layouts"] or not set(config["layouts"]).issubset(SUPPORTED_LAYOUTS):
        raise ValueError("layouts must contain supported layout names")
    if not config["themes"] or not set(config["themes"]).issubset(THEME_STYLES):
        raise ValueError("themes must contain supported theme names")
    minimum_quality = int(config["jpeg_quality_min"])
    maximum_quality = int(config["jpeg_quality_max"])
    if not 1 <= minimum_quality <= maximum_quality <= 100:
        raise ValueError("jpeg quality must be between 1 and 100")


def _composition(rng: random.Random, materials: list[str]) -> dict[str, int]:
    material_count = rng.choice((1, 2, 2, 3))
    selected = rng.sample(materials, material_count)
    if material_count == 1:
        return {selected[0]: 100}
    cuts = sorted(rng.sample(range(5, 100), material_count - 1))
    values = [cuts[0], *(right - left for left, right in zip(cuts, cuts[1:])), 100 - cuts[-1]]
    return dict(zip(selected, values, strict=True))


def build_specs(config: dict[str, Any]) -> list[LabelSpec]:
    rng = random.Random(int(config["seed"]))
    specs: list[LabelSpec] = []
    for index in range(int(config["base_label_count"])):
        language = config["languages"][index % len(config["languages"])]
        parts = {"outer": _composition(rng, config["materials"])}
        if rng.random() < float(config.get("lining_probability", 0.35)):
            parts["lining"] = _composition(rng, config["materials"])
        specs.append(
            LabelSpec(
                source_group=f"SYN{index + 1:04d}",
                language=language,
                parts=parts,
                layout=config["layouts"][index % len(config["layouts"])],
                theme=config["themes"][index % len(config["themes"])],
            )
        )
    return specs


def _font(language: str, size: int) -> tuple[ImageFont.FreeTypeFont | ImageFont.ImageFont, str]:
    for candidate in FONT_CANDIDATES[language]:
        try:
            return ImageFont.truetype(candidate, size=size), candidate
        except OSError:
            continue
    if language == "en":
        return ImageFont.load_default(), "Pillow-default"
    raise RuntimeError(
        f"{language} label font was not found. Configure a compatible system font before generation."
    )


def label_text(spec: LabelSpec) -> str:
    lines: list[str] = []
    for part, composition in spec.parts.items():
        names_and_ratios = [
            (MATERIAL_NAMES[spec.language][material], ratio)
            for material, ratio in composition.items()
        ]
        part_name = PART_NAMES[spec.language][part]
        if spec.layout == "material_first":
            values = " ".join(
                f"{material} {ratio}%" for material, ratio in names_and_ratios
            )
            lines.append(f"{part_name}: {values}")
        elif spec.layout == "ratio_first":
            values = " ".join(
                f"{ratio}% {material}" for material, ratio in names_and_ratios
            )
            lines.append(f"{part_name}: {values}")
        else:
            lines.append(part_name)
            lines.extend(material for material, _ in names_and_ratios)
            lines.extend(f"{ratio}%" for _, ratio in names_and_ratios)
    return "\n".join(lines)


def _draw_label(spec: LabelSpec, config: dict[str, Any]) -> tuple[Image.Image, str]:
    width, height = int(config["image_width"]), int(config["image_height"])
    style = THEME_STYLES[spec.theme]
    image = Image.new("RGB", (width, height), style["background"])
    draw = ImageDraw.Draw(image)
    font, font_name = _font(spec.language, int(config.get("font_size", 38)))
    text = label_text(spec)
    top = int(height * 0.2)
    for line in text.splitlines():
        draw.text((60, top), line, fill=style["foreground"], font=font)
        bbox = draw.textbbox((60, top), line, font=font)
        top += max(55, bbox[3] - bbox[1] + 22)
    draw.rectangle(
        (30, 30, width - 30, height - 30),
        outline=style["foreground"],
        width=2,
    )
    return image, font_name


def _apply_condition(
    image: Image.Image,
    condition: str,
    seed: int,
) -> tuple[Image.Image, dict[str, float | int]]:
    rng = random.Random(seed)
    result = image
    transforms: dict[str, float | int] = {}
    background = image.getpixel((0, 0))
    if condition == "clean":
        return result, transforms
    if condition in {"rotation", "mixed"}:
        angle = rng.choice((-7, -5, 5, 7))
        result = result.rotate(angle, fillcolor=background)
        transforms["rotation_degrees"] = angle
    if condition in {"perspective", "mixed"}:
        shear = rng.choice((-0.12, 0.12))
        result = result.transform(
            result.size,
            Image.Transform.AFFINE,
            (1, shear, -shear * result.height / 2, 0, 1, 0),
            fillcolor=background,
        )
        transforms["perspective_shear"] = shear
    if condition in {"blur", "mixed"}:
        blur_radius = 1.4 if condition == "blur" else 1.8
        result = result.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        transforms["blur_radius"] = blur_radius
    if condition in {"low_light", "mixed"}:
        brightness = 0.58 if condition == "low_light" else 0.72
        result = ImageEnhance.Brightness(result).enhance(brightness)
        transforms["brightness"] = brightness
    if condition in {"glare", "mixed"}:
        overlay = Image.new("RGBA", result.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        x = rng.randint(result.width // 4, result.width // 2)
        opacity = 85 if condition == "glare" else 105
        draw.ellipse(
            (x, 80, x + result.width // 3, result.height - 80),
            fill=(255, 255, 255, opacity),
        )
        result = Image.alpha_composite(result.convert("RGBA"), overlay).convert("RGB")
        transforms["glare_opacity"] = opacity
        transforms["glare_x"] = x
    return result, transforms


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _prepare_output(output_dir: Path) -> None:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Synthetic output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)


def _save_contact_sheet(rows: list[dict[str, str]], images_dir: Path, output_path: Path) -> None:
    thumbnails: list[tuple[Image.Image, str]] = []
    for row in rows:
        image_path = images_dir / row["file_name"]
        thumbnail = Image.open(image_path).convert("RGB")
        thumbnail.thumbnail((240, 160))
        caption = f'{row["source_group"]} {row["layout"]}/{row["condition"]}'
        thumbnails.append((thumbnail, caption))
    columns = 4
    rows = max(1, (len(thumbnails) + columns - 1) // columns)
    sheet = Image.new("RGB", (columns * 240, rows * 184), "white")
    draw = ImageDraw.Draw(sheet)
    for index, (thumbnail, caption) in enumerate(thumbnails):
        x = (index % columns) * 240
        y = (index // columns) * 184
        sheet.paste(thumbnail, (x, y))
        draw.text((x + 4, y + 164), caption, fill="black")
    sheet.save(output_path, quality=90)


def generate_dataset(config: dict[str, Any], output_dir: str | Path) -> dict[str, Any]:
    validate_config(config)
    output_path = Path(output_dir)
    _prepare_output(output_path)
    images_dir = output_path / "images"
    images_dir.mkdir()

    rows: list[dict[str, str]] = []
    for source_index, spec in enumerate(build_specs(config), start=1):
        for variant in range(int(config["variants_per_label"])):
            condition = config["conditions"][(source_index + variant - 1) % len(config["conditions"])]
            sample_seed = int(config["seed"]) + source_index * 10_000 + variant
            image, font_name = _draw_label(spec, config)
            image, transforms = _apply_condition(image, condition, sample_seed)
            file_name = f"{spec.source_group}_v{variant + 1:02d}.jpg"
            image_path = images_dir / file_name
            jpeg_quality = random.Random(sample_seed).randint(
                int(config["jpeg_quality_min"]),
                int(config["jpeg_quality_max"]),
            )
            image.save(image_path, quality=jpeg_quality)
            selected = spec.parts["outer"]
            rows.append(
                {
                    "file_name": file_name,
                    "source_group": spec.source_group,
                    "split": "unassigned",
                    "include_in_accuracy": "false",
                    "language": spec.language,
                    "condition": condition,
                    "layout": spec.layout,
                    "theme": spec.theme,
                    "jpeg_quality": str(jpeg_quality),
                    "transforms_json": json.dumps(transforms, sort_keys=True),
                    "answer_materials": ";".join(selected),
                    "answer_ratios": ";".join(str(value) for value in selected.values()),
                    "selected_part": "outer",
                    "parts_json": json.dumps(spec.parts, ensure_ascii=False, sort_keys=True),
                    "original_text": label_text(spec),
                    "font": font_name,
                    "seed": str(sample_seed),
                    "image_sha256": _sha256(image_path),
                }
            )

    manifest_path = output_path / "manifest.csv"
    with manifest_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (output_path / "config_resolved.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    summary = {
        "version": config["version"],
        "seed": config["seed"],
        "source_group_count": len({row["source_group"] for row in rows}),
        "image_count": len(rows),
        "condition_counts": {
            condition: sum(row["condition"] == condition for row in rows)
            for condition in config["conditions"]
        },
        "layout_counts": {
            layout: sum(row["layout"] == layout for row in rows)
            for layout in config["layouts"]
        },
        "theme_counts": {
            theme: sum(row["theme"] == theme for row in rows)
            for theme in config["themes"]
        },
    }
    (output_path / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    _save_contact_sheet(rows, images_dir, output_path / "contact_sheet.jpg")
    return {"output_dir": str(output_path), **summary}
