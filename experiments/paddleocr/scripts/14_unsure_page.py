"""2단계: '확인 필요' 줄을 사람이 훑어볼 수 있게 잘라낸 이미지와 제 읽기를 나란히 보여 주는 HTML을 만든다.

결과: data/stage2/unsure_review.html (브라우저로 열기). 고칠 줄은 labels_corrections.tsv에 같은 형식으로 덧붙이면 된다.
"""
import csv
import html
from pathlib import Path

S2 = Path(__file__).absolute().parents[1] / "data" / "stage2"
rows = list(csv.DictReader((S2 / "unsure_list.tsv").open(encoding="utf-8"), delimiter="\t",
                               quoting=csv.QUOTE_NONE))  # 13이 따옴표 처리 없이 쓴 TSV라 따옴표를 글자로 읽는다
out = ["<!doctype html><meta charset='utf-8'><title>확인 필요 줄</title>",
       "<style>body{font-family:'Malgun Gothic',sans-serif;margin:16px}td{border-bottom:1px solid #ddd;padding:4px 8px}"
       "img{max-height:48px;max-width:600px}</style>",
       f"<h2>확인 필요 줄 {len(rows)}개</h2><p>글자가 사진과 다르면 labels_corrections.tsv 끝에 "
       "<code>줄ID[탭]ok[탭]고친 글자[탭]메모</code>를 덧붙이세요. 판독 불가면 status를 exclude로.</p><table>"]
for r in rows:
    out.append(f"<tr><td>{r['line_id']}</td><td><img src='{html.escape(r['crop'])}'></td>"
               f"<td><b>{html.escape(r['best_reading'])}</b></td><td>{html.escape(r['note'])}</td></tr>")
out.append("</table>")
(S2 / "unsure_review.html").write_text("\n".join(out), encoding="utf-8")
print(len(rows))
