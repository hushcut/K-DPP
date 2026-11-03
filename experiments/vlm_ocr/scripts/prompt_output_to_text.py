"""표·JSON 출력을 서비스 파서가 읽는 글자 줄로 바꾼 결과 폴더를 새로 만든다. 원본 결과 폴더는 읽기만 한다.

- table: PaddleOCR-VL의 표 태그(<fcel> 등)와 GLM-OCR의 HTML 표를 칸은 공백, 행은 줄바꿈으로 바꾼다.
- json: {"composition": [{"material": ..., "percent": ...}]} 형식이면 "소재 비율" 줄로 바꾼다. 형식을 어겼으면 JSON 기호만 지운다.
"""
import argparse
import json
from pathlib import Path
import re
import shutil

TABLE_CELLS = re.compile(r"<(?:fcel|ecel|lcel|ucel|xcel)>|</?td[^>]*>|</?th[^>]*>|</?table>|</?tbody>|</?thead>|<tr>")
TABLE_ROWS = re.compile(r"<nl>|</tr>")
JSON_FENCE = re.compile(r"```(?:json)?")
JSON_PAIR = re.compile(r'"?material"?\s*:\s*"([^"\n]*)"?\s*,\s*"?percent"?\s*:\s*"([^"\n]*)"?')
JSON_KEY = re.compile(r'"?composition"?\s*:')
JSON_VALUE_PAIR = re.compile(r'"([^"\n]*)"\s*:\s*"([^"\n]*)"')
JSON_MARKS = re.compile(r'[{}\[\]"]|,\s*$')


def table_to_text(text):
    text = TABLE_ROWS.sub("\n", text.replace("\\n", "\n"))
    lines = [" ".join(TABLE_CELLS.sub(" ", line).split()) for line in text.split("\n")]
    return "\n".join(line for line in lines if line), True


def json_to_text(text):
    # 요청한 형식을 지킨 출력만 ok로 센다. 모델이 자주 내는 문자열 목록·깨진 JSON은 기호를 걷어 글자 줄로 남긴다.
    match = re.search(r"\{.*\}", text, re.S)
    try:
        rows = json.loads(match.group(0))["composition"] if match else None
        lines = [f"{row['material']} {row['percent']}".strip() for row in rows]
        return "\n".join(line for line in lines if line), True
    except (ValueError, KeyError, TypeError):
        pass
    text = JSON_FENCE.sub(" ", text)
    text = JSON_PAIR.sub(r"\1 \2", text)
    text = JSON_KEY.sub(" ", text)
    text = JSON_VALUE_PAIR.sub(r"\1 \2", text)
    lines = [" ".join(JSON_MARKS.sub(" ", line).split()) for line in text.split("\n")]
    return "\n".join(line for line in lines if line), False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--kind", required=True, choices=("table", "json"))
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("기존 결과를 덮어쓰지 않습니다.")
    convert = table_to_text if args.kind == "table" else json_to_text
    args.output.mkdir(parents=True)
    converted = failed = 0
    for folder in sorted(p for p in args.input.iterdir() if (p / "result.json").exists()):
        out = args.output / folder.name
        out.mkdir()
        meta = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        text, ok = convert((folder / "text.txt").read_text(encoding="utf-8").strip())
        converted += ok
        failed += not ok
        meta.update({"postprocess": f"{args.kind}_to_text", "postprocess_ok": ok, "postprocess_input": str(folder), "text": text})
        (out / "result.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "text.txt").write_text(text + "\n", encoding="utf-8")
    shutil.copy2(args.input / "run_config.json", args.output / "input_run_config.json")
    print(json.dumps({"format_followed": converted, "format_broken": failed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
