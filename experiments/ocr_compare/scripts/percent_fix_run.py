"""EasyOCR이 `%`를 `96`으로 읽는 오독만 고친 글자 결과 폴더를 새로 만든다(진단용 후처리 시험).

- 규칙: 앞에 숫자가 없는 1~3자리 수 뒤의 `96`을 `%`로 바꾼다(그 수가 100 이하일 때만, 예: 6596→65%).
  `%` 바로 뒤에 붙은 `6`은 지운다(예: 100%6→100%).
- 원본 결과 폴더는 읽기만 하고, result.json에는 후처리 이름과 바뀐 횟수를 더해 새 폴더에 쓴다.
"""
import argparse
import json
import re
import shutil
from pathlib import Path

NUMBER_96 = re.compile(r"(?<!\d)(\d{1,3})96(?!\d)")
TRAILING_6 = re.compile(r"(?<=\d%)6(?!\d)")


def fix(text):
    count = 0

    def percent(match):
        nonlocal count
        if int(match.group(1)) > 100:
            return match.group(0)
        count += 1
        return match.group(1) + "%"

    text = NUMBER_96.sub(percent, text)
    text, trailing = TRAILING_6.subn("", text)
    return text, count + trailing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("기존 결과를 덮어쓰지 않습니다.")
    args.output.mkdir(parents=True)
    changed = {}
    for folder in sorted(p for p in args.input.iterdir() if (p / "result.json").exists()):
        out = args.output / folder.name
        out.mkdir()
        meta = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        text, count = fix((folder / "text.txt").read_text(encoding="utf-8"))
        meta.update({"postprocess": "percent_fix_v1", "postprocess_changes": count, "postprocess_input": str(folder)})
        meta.pop("lines", None)
        (out / "result.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "text.txt").write_text(text, encoding="utf-8")
        changed[folder.name] = count
    if (args.input / "run_config.json").exists():
        shutil.copy2(args.input / "run_config.json", args.output / "input_run_config.json")
    print(json.dumps({"photos": len(changed), "photos_changed": sum(c > 0 for c in changed.values()),
                      "changes": sum(changed.values())}, ensure_ascii=False))


if __name__ == "__main__":
    main()
