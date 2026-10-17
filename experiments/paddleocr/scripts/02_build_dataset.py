"""2단계: 사람이 확인한 라벨로 학습/검증 목록을 만든다.

라벨은 사진에 적힌 그대로다 (POLY는 POLY). 확인이 어려운 줄은 제외 목록에 이유와 함께 남긴다.
검증 줄도 같은 사진(01~05)에서 나온 것이라 독립 평가가 아니다. 이번 목적은 학습 흐름 확인뿐이다.
"""
import json
from pathlib import Path

EXP = Path(__file__).absolute().parents[1]
DATA = EXP / "data"

# crop 파일 → 확인한 라벨, 확인 상태 (ok / unsure)
LABELS = {
    "01_02": ("해병대 기능성 런닝", "ok"),
    "01_03": ("품 명", "unsure"),  # 글자 간격이 넓음: 공백 표기 기준 확인 필요
    "01_04": ("100호", "ok"),
    "01_05": ("호 칭", "unsure"),
    "01_06": ("폴리에스터94%, 폴리우레탄6%", "unsure"),  # 첫 글자 '폴'이 잘려 있음
    "01_07": ("혼용률", "unsure"),  # 가운데 글자가 가려짐
    "01_08": ("주의사항", "ok"),
    "01_09": ("취급상", "unsure"),  # 가운데 글자가 흐림
    "01_12": ("약30°C", "unsure"),  # 첫 글자 일부 잘림
    "02_00": ("GRATEFUL DAYS.", "ok"),
    "02_01": ("POLY 100%", "ok"),
    "02_03": ("HAND WASH DRY", "ok"),
    "02_04": ("UNIONOBJET", "ok"),
    "02_05": ("DO NOT BLEACH", "ok"),
    "02_06": ("DO NOT IRON", "ok"),
    "02_07": ("MADE IN KOREA", "ok"),
    "02_09": ("DO NOT TUMBLE DRY", "ok"),
    "02_10": ("DO NOT DRYCLEAN", "ok"),
    "03_01": ("전기용품 및 생활용품", "ok"),
    "03_02": ("안전관리법에 따른 품질표시", "ok"),
    "03_03": ("KR 겉감: 면 100%", "ok"),
    "03_04": ("심지, 상표, 보강재, 자수, 장식 제외 /", "ok"),
    "04_01": ("THE MUSEUM VISITOR", "ok"),
    "04_02": ("FABRIC COMPOSITION", "ok"),
    "04_03": ("100% Cotton", "ok"),
    "04_04": ("Hand Wash", "ok"),
    "04_05": ("do", "ok"),
    "04_06": ("not bleach", "ok"),
    "04_07": ("do", "ok"),
    "04_08": ("not tumble", "ok"),
    "04_09": ("dry", "ok"),
    "05_00": ("COTTON 100%", "ok"),
    "05_01": ("CARE INSTRUCTIONS", "ok"),
    "05_04": ("DO NOT WASH", "ok"),
    "05_05": ("DO NOT DRY", "ok"),
    "05_06": ("DO NOT IRON", "ok"),
    "05_07": ("DO NOT DRYCLEAN", "ok"),
    "05_08": ("DO NOT BLEACH", "ok"),
    "05_09": ("MADE IN KOREA", "ok"),
    "05_10": ("elldu.com", "ok"),
}
EXCLUDED = {
    "01_00": "세로로 돌아간 조각, 글자 판독 불가",
    "01_01": "글자 판독 불가",
    "01_11": "기호 조각",
    "02_08": "URL 일부가 잘리고 흐림",
    "03_00": "O/0 구분 불가한 품번",
    "03_05": "일본어·중국어(装飾を除く/饰边除外)가 한국어 사전에 없음",
    "04_00": "뒤집힌 부분 조각",
    "05_03": "세탁기호(범위 제외)",
}
# 검증용: 사진마다 1~2줄. 같은 사진에서 나와 독립 평가가 아님
VAL = {"01_08", "02_05", "03_02", "04_06", "05_09", "02_01"}


def main():
    dict_chars = set((EXP / "downloads/main_cfg/ppocrv5_korean_dict.txt").read_text(encoding="utf-8").splitlines()) | {" "}
    train, val = [], []
    for key, (text, _) in sorted(LABELS.items()):
        missing = [c for c in text if c not in dict_chars]
        assert not missing, (key, missing)
        line = f"crops/{key}.jpg\t{text}"
        (val if key in VAL else train).append(line)
    (DATA / "train_list.txt").write_text("\n".join(train) + "\n", encoding="utf-8")
    (DATA / "val_list.txt").write_text("\n".join(val) + "\n", encoding="utf-8")
    review = {"labels": {k: {"text": t, "status": s, "split": "val" if k in VAL else "train"}
                         for k, (t, s) in sorted(LABELS.items())},
              "excluded": EXCLUDED,
              "photos_used": ["01", "02", "03", "04", "05"]}
    (DATA / "labels_reviewed.json").write_text(json.dumps(review, ensure_ascii=False, indent=1), encoding="utf-8")
    print("train", len(train), "val", len(val), "unsure", sum(s == "unsure" for _, s in LABELS.values()))


if __name__ == "__main__":
    main()
