"""기본 검출·인식 모델로 원본 사진 한 장을 읽고 결과를 별도 폴더에 기록한다."""
import argparse
import hashlib
import importlib
import json
import platform
import time
from importlib.metadata import version
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--textline-orientation", action="store_true",
                        help="잘라낸 줄마다 0/180도 방향을 분류해 180도면 뒤집는다 "
                             "(PaddleOCR use_textline_orientation=True와 같은 모델·규칙)")
    # 검출 설정. 지정하지 않으면 모델 기본값(긴 변 960 축소, thresh 0.3, box_thresh 0.6, unclip 1.5)
    parser.add_argument("--det-limit-side-len", type=int)
    parser.add_argument("--det-limit-type", choices=("max", "min"))
    parser.add_argument("--det-thresh", type=float)
    parser.add_argument("--det-box-thresh", type=float)
    parser.add_argument("--det-unclip-ratio", type=float)
    args = parser.parse_args()
    det_params = {key: value for key, value in {
        "limit_side_len": args.det_limit_side_len, "limit_type": args.det_limit_type,
        "thresh": args.det_thresh, "box_thresh": args.det_box_thresh,
        "unclip_ratio": args.det_unclip_ratio}.items() if value is not None}
    if args.output_dir.exists():
        raise FileExistsError("결과 폴더가 이미 있습니다. 새 출력 경로를 지정하세요.")
    image_hash = hashlib.sha256(args.image.read_bytes()).hexdigest()
    exp = Path(__file__).absolute().parents[1]
    started = time.perf_counter()
    baseline = importlib.import_module("10_stage2_baseline_run")
    image = baseline.imread_unicode(args.image)
    if image is None:
        raise ValueError("입력 이미지를 읽지 못했습니다.")
    original_hw = list(image.shape[:2])
    scale = min(1.0, 1600 / max(original_hw))
    if scale < 1:
        image = baseline.cv2.resize(image, None, fx=scale, fy=scale,
                                    interpolation=baseline.cv2.INTER_AREA)
    load_started = time.perf_counter()
    detector = baseline.TextDetection(
        model_name="PP-OCRv5_server_det",
        model_dir=str(exp / "models/base/PP-OCRv5_server_det_infer"),
        device="cpu", enable_mkldnn=False, **det_params,
    )
    recognizer = baseline.TextRecognition(
        model_name="korean_PP-OCRv5_mobile_rec",
        model_dir=str(exp / "models/base/korean_PP-OCRv5_mobile_rec_infer"),
        device="cpu", enable_mkldnn=False,
    )
    orientation_model = "PP-LCNet_x1_0_textline_ori" if args.textline_orientation else None
    classifier = None
    if orientation_model:
        from paddleocr import TextLineOrientationClassification
        classifier = TextLineOrientationClassification(
            model_name=orientation_model,
            model_dir=str(exp / f"models/base/{orientation_model}_infer"),
            device="cpu", enable_mkldnn=False,
        )
    load_seconds = time.perf_counter() - load_started
    inference_started = time.perf_counter()
    detected = list(detector.predict(image))[0]
    polygons = sorted(detected["dt_polys"], key=lambda q: (q[:, 1].min(), q[:, 0].min()))
    kept, skipped = [], []
    for index, polygon in enumerate(polygons):
        crop, rotated = baseline.crop_quad(image, polygon)
        entry = {"index": index, "polygon": polygon.tolist(), "rotated": rotated,
                 "crop_hw": list(crop.shape[:2])}
        if crop.shape[0] < 12 or crop.shape[1] < 24:
            skipped.append({**entry, "reason": "too_small"})
        else:
            kept.append((entry, crop))
    if classifier and kept:
        angles = list(classifier.predict([crop for _, crop in kept]))
        if len(angles) != len(kept):
            raise RuntimeError("글자 영역 수와 방향 분류 결과 수가 다릅니다.")
        for i, ((entry, crop), angle) in enumerate(zip(kept, angles)):
            flipped = int(angle["class_ids"][0]) == 1  # 0: 0도, 1: 180도
            entry["textline_angle"] = 180 if flipped else 0
            entry["textline_angle_score"] = round(float(angle["scores"][0]), 4)
            if flipped:
                kept[i] = (entry, baseline.cv2.rotate(crop, baseline.cv2.ROTATE_180))
    predictions =list(recognizer.predict([crop for _, crop in kept])) if kept else []
    if len(predictions) != len(kept):
        raise RuntimeError("글자 영역 수와 인식 결과 수가 다릅니다.")
    lines = [{**entry, "text": result["rec_text"].strip(),
              "score": round(float(result["rec_score"]), 4)}
             for (entry, _), result in zip(kept, predictions)]
    inference_seconds = time.perf_counter() - inference_started
    unchanged = hashlib.sha256(args.image.read_bytes()).hexdigest() == image_hash
    if not unchanged:
        raise RuntimeError("실행 전후 원본 이미지 해시가 다릅니다.")
    result = {
        "source_name": args.image.name, "source_sha256": image_hash,
        "source_unchanged": unchanged, "original_hw": original_hw, "scale": scale,
        "python": platform.python_version(),
        "packages": {name: version(name) for name in
                     ("paddlepaddle", "paddleocr", "paddlex", "numpy", "opencv-contrib-python")},
        "device": "cpu", "enable_mkldnn": False,
        "det_model": "PP-OCRv5_server_det", "rec_model": "korean_PP-OCRv5_mobile_rec",
        "det_params": det_params,
        "textline_orientation_model": orientation_model,
        "flipped_180_lines": sum(line.get("textline_angle") == 180 for line in lines),
        "detected_lines": len(polygons), "recognized_lines": len(lines), "skipped": skipped,
        "model_load_seconds": round(load_seconds, 3),
        "inference_seconds": round(inference_seconds, 3),
        "total_seconds": round(time.perf_counter() - started, 3), "lines": lines,
    }
    args.output_dir.mkdir(parents=True)
    (args.output_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output_dir / "text.txt").write_text(
        "\n".join(line["text"] for line in lines) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "lines"},
                     ensure_ascii=False, indent=2))
    for line in lines:
        print(f"{line['score']:.4f}\t{line['text']}")


if __name__ == "__main__":
    main()