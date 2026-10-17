"""2단계 검토용: 사진마다 잘라낸 줄 이미지 옆에 기본 모델이 읽은 글자(초안)를 붙인 확인용 그림을 만든다.

사용법: venv\\Scripts\\python.exe scripts\\11_make_review_sheets.py [사진ID ...]  (없으면 아직 안 만든 사진 전부)
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

EXP = Path(__file__).absolute().parents[1]
S2 = EXP / "data" / "stage2"
OUT = S2 / "review"
FONT = ImageFont.truetype(r"C:\Windows\Fonts\malgun.ttf", 20)
ROW_H, CROP_W, TEXT_W = 56, 760, 620


def sheet(pid):
    d = json.loads((S2 / "photos" / f"{pid}.json").read_text(encoding="utf-8"))
    lines = [l for l in d["lines"] if "crop" in l]
    canvas = Image.new("RGB", (CROP_W + TEXT_W, max(1, len(lines)) * ROW_H), "white")
    draw = ImageDraw.Draw(canvas)
    for k, l in enumerate(lines):
        im = Image.open(S2 / l["crop"]).convert("RGB")
        s = min((ROW_H - 6) / im.height, (CROP_W - 70) / im.width)
        im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))))
        y = k * ROW_H
        canvas.paste(im, (66, y + 3))
        draw.text((2, y + 14), l["line_id"][-3:], fill="blue", font=FONT)
        draw.text((CROP_W + 6, y + 4), l["draft"], fill="black", font=FONT)
        draw.text((CROP_W + 6, y + 30), f"{l['score']:.2f}", fill="gray", font=ImageFont.truetype(r"C:\Windows\Fonts\malgun.ttf", 14))
        draw.line([(0, y + ROW_H - 1), (CROP_W + TEXT_W, y + ROW_H - 1)], fill=(220, 220, 220))
    OUT.mkdir(exist_ok=True)
    canvas.save(OUT / f"{pid}.png")


if __name__ == "__main__":
    ids = sys.argv[1:] or [p.stem for p in sorted((S2 / "photos").glob("*.json"))
                           if not (OUT / f"{p.stem}.png").exists()]
    for pid in ids:
        sheet(pid)
        print(pid)
