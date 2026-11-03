"""서비스의 소재 영역 찾기 코드로 사진의 조성 영역을 잘라 VLM 입력 이미지를 만든다. OCR을 새로 호출하지 않는다.

- 좌표는 저장된 서비스 OCR 캐시(Vision 또는 PaddleOCR)의 원본 후보 단어만 쓴다.
- --region all_text는 글자 내용을 보지 않고 글자 상자 전체를 감싼 영역이다. 글자 인식 없이 검출만으로 만들 수 있는 영역을 흉내 낸다.
- 영역을 못 찾은 사진은 목록에서 빠진다. 채점할 때 전체 사진 결과로 대신한다(region_eval.py).
- 자른 이미지는 무손실 PNG로 저장하고 크기는 그대로 둔다. 축소는 run_images.py의 --max-pixels가 맡는다.

실행 예: <서비스 .venv python> -I -X utf8 make_region_crops.py --service-dir <서비스 코드> --photos <사진 폴더> \\
          --manifest <사진 목록 JSON> --ocr-cache <OCR 캐시 JSON> --output <새 폴더>
"""
import argparse
import hashlib
from io import BytesIO
import json
import math
from pathlib import Path
import socket
import statistics
import sys
from types import SimpleNamespace

from PIL import Image, ImageOps

MIN_DESKEW_DEGREES = 5
ALL_TEXT_MARGIN_LINES = 1


def all_text_region(words, width, height):
    margin = ALL_TEXT_MARGIN_LINES * statistics.median(word.bottom - word.top for word in words)
    return (max(0, math.floor(min(word.left for word in words) - margin)),
            max(0, math.floor(min(word.top for word in words) - margin)),
            min(width, math.ceil(max(word.right for word in words) + margin)),
            min(height, math.ceil(max(word.bottom for word in words) + margin)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service-dir", required=True, type=Path)
    parser.add_argument("--photos", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path, help="id/source/sha256 목록 JSON")
    parser.add_argument("--ocr-cache", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--region", choices=("material", "all_text"), default="material")
    parser.add_argument("--deskew", action="store_true",
                        help=f"글자 기울기가 {MIN_DESKEW_DEGREES}도 이상인 영역을 서비스 소재 영역 후보처럼 바로 세운다.")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("결과 폴더가 이미 있습니다. 새 출력 경로를 지정하세요.")

    def blocked(*a, **kw):
        raise RuntimeError("영역 자르기는 외부 네트워크를 쓰지 않습니다.")
    socket.socket.connect = blocked
    socket.create_connection = blocked
    sys.path.insert(0, str(args.service_dir))
    from apps.text.ocr_cache import decode_layout_words
    from apps.text.ocr_image import validate_image_bytes
    from apps.text.ocr_regions import find_material_region, material_region_options

    entries = json.loads(args.ocr_cache.read_text(encoding="utf-8"))["entries"].values()
    originals = {entry["file_name"]: entry for entry in entries if entry["source"] == "original"}
    images = args.output / "images"
    images.mkdir(parents=True)
    crops, missing = [], []
    for item in json.loads(args.manifest.read_text(encoding="utf-8")):
        content = (args.photos / item["source"]).read_bytes()
        if hashlib.sha256(content).hexdigest() != item["sha256"]:
            raise RuntimeError(f"{item['id']}: 사진 목록의 해시와 원본이 다릅니다.")
        entry = originals.get(item["source"])
        validated = validate_image_bytes(content)
        words = decode_layout_words(entry) if entry else ()
        # find_material_region은 후보의 좌표 필드만 읽는다.
        candidate = SimpleNamespace(image_key="original", image_variant_key="original",
                                    image_region=(0, 0, validated.width, validated.height), image_words=words)
        if not words:
            box = None
        elif args.region == "all_text":
            box = all_text_region(words, validated.width, validated.height)
        else:
            box = find_material_region([candidate], validated.width, validated.height)
        if box is None:
            missing.append({"id": item["id"], "reason": "no_cache" if not entry else "no_region"})
            continue
        font_height, angle = material_region_options([candidate], box)
        with Image.open(BytesIO(validated.content)) as image:
            upright = ImageOps.exif_transpose(image).convert("RGB")
        if upright.size != (validated.width, validated.height):
            raise RuntimeError(f"{item['id']}: 좌표 기준과 이미지 크기가 다릅니다.")
        crop = upright.crop(box)
        rotated = args.deskew and abs(angle) >= MIN_DESKEW_DEGREES
        if rotated:
            crop = crop.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=(255, 255, 255))
        buffer = BytesIO()
        crop.save(buffer, format="PNG")
        name = f"{item['id']}.png"
        (images / name).write_bytes(buffer.getvalue())
        area = (box[2] - box[0]) * (box[3] - box[1])
        crops.append({"id": item["id"], "source": name, "sha256": hashlib.sha256(buffer.getvalue()).hexdigest(),
                      "parent_source": item["source"], "parent_sha256": item["sha256"], "box": list(box),
                      "output_size": list(crop.size), "area_share": round(area / (validated.width * validated.height), 4),
                      "font_height": font_height, "angle": angle, "rotated": rotated})
    (args.output / "manifest.json").write_text(json.dumps(crops, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output / "missing.json").write_text(json.dumps(missing, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.deskew:
        # 돌리지 않은 사진은 기존 자른 결과와 같은 이미지라서 돌린 사진만 다시 읽으면 된다.
        (args.output / "manifest_rotated.json").write_text(
            json.dumps([c for c in crops if c["rotated"]], ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"photos": len(crops) + len(missing), "crops": len(crops), "missing": len(missing),
                      "rotated": sum(c["rotated"] for c in crops),
                      "median_area_share": round(statistics.median(c["area_share"] for c in crops), 3)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
