"""사진 분석(Google Vision) 하루 상한(DECISIONS 164).

Vision 을 부르는 스캔만 세고, 한 계정 하루 SCAN_USER_DAILY_MAX 번·서버 전체 하루
SCAN_DAILY_MAX 번(환경변수, 비우면 없음)에서 막는다. 하루는 한국 자정에 바뀐다.
상한은 사용자 id 만 보므로, 인증은 get_current_user 를 바꿔 끼워 건너뛴다(인증은 다른 테스트가 본다).
"""

import threading
import time
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import main
from process_helpers import run_python


LABEL = ("label.jpg", b"test-image", "image/jpeg")
# 2026-10-07 03:00 UTC = 10-07 12:00 KST. 실제 시계를 쓰면 한국 자정을 걸친 실행에서 흔들린다.
NOON_KST = datetime(2026, 10, 7, 3, 0, 0)


def set_clock(monkeypatch, moment):
    monkeypatch.setattr(main, "utc_now", lambda: moment)


@pytest.fixture()
def vision(client, monkeypatch):
    """가짜 Vision: 부른 임시 파일 경로를 모은다. 기본은 소재를 다 읽은 라벨 문자열을 돌려준다."""
    calls = []

    def fake_run_ocr(image_path, credential_path=""):
        calls.append(image_path)
        return "COTTON 100%"

    monkeypatch.setattr(main, "run_ocr", fake_run_ocr)
    set_clock(monkeypatch, NOON_KST)
    yield calls
    main.app.dependency_overrides.pop(main.get_current_user, None)


def scan(client, user_id, image=LABEL, **data):
    main.app.dependency_overrides[main.get_current_user] = lambda: SimpleNamespace(id=user_id)
    return client.post("/api/scan", files={"image": image}, data=data)


def use_up(client, user_id, times):
    for _ in range(times):
        assert scan(client, user_id).status_code == 200


def counts_today():
    (counts,) = main._vision_scan_counts.values()
    return counts


def test_user_cap_is_twenty():
    # 계약 문서·청구 최악값 계산(DECISIONS 164)이 이 값을 쓴다.
    assert main.SCAN_USER_DAILY_MAX == 20


def test_vision_scans_stop_at_daily_cap(client, vision):
    use_up(client, 1, main.SCAN_USER_DAILY_MAX)
    assert len(vision) == main.SCAN_USER_DAILY_MAX

    response = scan(client, 1)

    assert response.status_code == 429
    body = response.json()
    assert body["error_code"] == "SCAN_DAILY_LIMIT"
    assert "하루 20번" in body["message"]
    # 12:00 KST 에 막히면 다음 한국 자정까지 12시간.
    assert body["detail"]["retry_after"] == 12 * 60 * 60
    # 막힌 요청은 Vision 을 부르지 않고 세지도 않는다.
    assert len(vision) == main.SCAN_USER_DAILY_MAX
    assert counts_today() == {1: main.SCAN_USER_DAILY_MAX}


def test_cap_is_per_user(client, vision):
    use_up(client, 1, main.SCAN_USER_DAILY_MAX)

    assert scan(client, 1).status_code == 429
    assert scan(client, 2).status_code == 200


def test_raw_ocr_text_scans_are_not_counted(client, vision):
    # OCR 을 건너뛴 요청은 Vision 비용이 없어 상한을 넘겨도 된다.
    for _ in range(main.SCAN_USER_DAILY_MAX + 5):
        response = scan(client, 1, raw_ocr_text="COTTON 80% POLYESTER 20%")
        assert response.status_code == 200
    assert vision == []
    assert not any(main._vision_scan_counts.values())

    # Vision 상한을 다 쓴 뒤에도 raw_ocr_text 요청은 그대로 된다.
    use_up(client, 1, main.SCAN_USER_DAILY_MAX)
    assert scan(client, 1).status_code == 429
    assert scan(client, 1, raw_ocr_text="COTTON 100%").status_code == 200


def test_rejected_uploads_and_missing_ai_modules_are_not_counted(client, vision, monkeypatch):
    unsupported = scan(client, 1, image=("label.gif", b"GIF89a", "image/gif"))
    too_large = scan(client, 1, image=("big.jpg", b"x" * (main.MAX_UPLOAD_BYTES + 1), "image/jpeg"))
    monkeypatch.setattr(main, "parse_label", None)
    no_parser = scan(client, 1)
    monkeypatch.setattr(main, "run_ocr", None)
    no_ocr = scan(client, 1)

    assert unsupported.status_code == 415
    assert too_large.status_code == 413
    # 파서가 없으면 Vision 을 불러도 503 이라, 부르기 전에 같은 503 을 낸다.
    assert no_parser.status_code == 503
    assert no_parser.json()["error_code"] == "AI_MODULE_FAILED"
    assert no_ocr.status_code == 503
    assert no_ocr.json()["error_code"] == "AI_MODULE_FAILED"
    assert vision == []
    assert not any(main._vision_scan_counts.values())


def test_long_upload_name_still_reaches_vision(client, vision):
    # 업로드 이름의 확장자로 임시 파일을 만들면 아주 긴 이름에서 500 이 났다(센 뒤에).
    response = scan(client, 1, image=("a." + "b" * 300, b"test-image", "image/jpeg"))

    assert response.status_code == 200
    assert len(vision) == 1 and vision[0].endswith(".jpg")
    assert counts_today() == {1: 1}


def test_failed_vision_calls_still_count(client, vision, monkeypatch):
    # Vision 이 실패하거나(502) 소재를 못 찾아도(422) 호출은 이미 일어났으니 되돌리지 않는다.
    def broken_ocr(image_path, credential_path=""):
        vision.append(image_path)
        raise RuntimeError("Vision 장애")

    monkeypatch.setattr(main, "run_ocr", broken_ocr)
    assert scan(client, 1).status_code == 502

    monkeypatch.setattr(main, "run_ocr", lambda image_path, credential_path="": "WASH COLD")
    assert scan(client, 1).status_code == 422

    assert counts_today() == {1: 2}


def test_cap_resets_at_korean_midnight(client, vision, monkeypatch):
    # 2026-10-07 14:59:59 UTC = 10-07 23:59:59 KST, 1초 뒤가 10-08 00:00 KST.
    set_clock(monkeypatch, datetime(2026, 10, 7, 14, 59, 59))
    use_up(client, 1, main.SCAN_USER_DAILY_MAX)
    blocked = scan(client, 1)
    assert blocked.status_code == 429
    assert blocked.json()["detail"]["retry_after"] == 1

    set_clock(monkeypatch, datetime(2026, 10, 7, 15, 0, 0))
    assert scan(client, 1).status_code == 200
    # 지난 날의 기록은 지운다.
    assert list(main._vision_scan_counts) == [datetime(2026, 10, 8).date()]


def test_korean_day_starts_at_midnight_not_utc(client, vision, monkeypatch):
    # 10-07 00:00 KST(= 10-06 15:00 UTC)에 다 쓰면 다음 한국 자정까지 꼬박 하루를 기다린다.
    set_clock(monkeypatch, datetime(2026, 10, 6, 15, 0, 0))
    use_up(client, 1, main.SCAN_USER_DAILY_MAX)
    assert scan(client, 1).json()["detail"]["retry_after"] == 24 * 60 * 60

    # UTC 날짜가 바뀌어도(10-07 00:00 UTC = 10-07 09:00 KST) 한국 날짜는 같아 그대로 막힌다.
    set_clock(monkeypatch, datetime(2026, 10, 7, 0, 0, 0))
    assert scan(client, 1).status_code == 429


@pytest.mark.parametrize(
    "moment, expected",
    [
        # 자정까지 1.5초 → 2초(내림하면 다시 보낸 요청이 아직 자정 전이라 또 막힘)
        (datetime(2026, 10, 7, 14, 59, 58, 500000), 2),
        # 자정까지 0.5초 → 1초(0 이 나가지 않게)
        (datetime(2026, 10, 7, 14, 59, 59, 500000), 1),
    ],
)
def test_retry_after_rounds_up(client, vision, monkeypatch, moment, expected):
    set_clock(monkeypatch, moment)
    use_up(client, 1, main.SCAN_USER_DAILY_MAX)

    assert scan(client, 1).json()["detail"]["retry_after"] == expected


def test_clock_going_back_keeps_later_day(client, vision, monkeypatch):
    # 시계가 자정 앞으로 돌아가도(또는 자정 직전 요청이 늦게 들어와도) 새 날 기록을 지우지 않는다.
    set_clock(monkeypatch, datetime(2026, 10, 7, 15, 0, 1))  # 10-08 00:00:01 KST
    use_up(client, 1, main.SCAN_USER_DAILY_MAX)
    assert scan(client, 1).status_code == 429

    set_clock(monkeypatch, datetime(2026, 10, 7, 14, 59, 59))  # 10-07 23:59:59 KST
    assert scan(client, 2).status_code == 200

    set_clock(monkeypatch, datetime(2026, 10, 7, 15, 0, 2))
    assert scan(client, 1).status_code == 429


def test_server_daily_cap_returns_503(client, vision, monkeypatch, capsys):
    monkeypatch.setattr(main, "SCAN_DAILY_MAX", 3)
    use_up(client, 1, 1)
    use_up(client, 2, 1)
    use_up(client, 3, 1)
    # 운영자가 언제 닿았는지 볼 수 있게 한국 시각을 남긴다.
    assert "[scan] 2026-10-07 12:00 KST" in capsys.readouterr().err

    for user_id in (1, 4):
        response = scan(client, user_id)
        assert response.status_code == 503
        body = response.json()
        assert body["error_code"] == "SCAN_UNAVAILABLE"
        assert body["detail"]["retry_after"] == 12 * 60 * 60
    assert len(vision) == 3
    assert sum(counts_today().values()) == 3
    # 상한에 닿았다는 기록은 그날 한 번만 남는다.
    assert "서버 전체" not in capsys.readouterr().err


def test_user_cap_is_reported_before_server_cap(client, vision, monkeypatch):
    monkeypatch.setattr(main, "SCAN_USER_DAILY_MAX", 2)
    monkeypatch.setattr(main, "SCAN_DAILY_MAX", 3)
    use_up(client, 1, 2)
    use_up(client, 2, 1)

    # 둘 다 막혔으면 자기 상한(429)을 알려 준다 — 서버 상한이 풀려도 그 사람은 못 쓴다.
    assert scan(client, 1).status_code == 429
    assert scan(client, 2).status_code == 503


class SlowDay(dict):
    """그날 기록에 새 수를 쓰기 직전에 잠깐 쉬어, 확인(사용자 수·서버 합계)과 쓰기 사이에 다른
    스레드가 끼어들 틈을 벌린다(GIL 아래에선 그 사이가 짧아 잠금을 빼도 경합이 거의 드러나지 않는다)."""

    def __init__(self):
        super().__init__()
        self.slow_writes = 0

    def __setitem__(self, key, value):
        self.slow_writes += 1
        time.sleep(0.005)
        super().__setitem__(key, value)


def reserve_from_threads(user_ids):
    barrier = threading.Barrier(len(user_ids))
    results = []

    def worker(user_id):
        barrier.wait()
        try:
            main.reserve_vision_scan(user_id)
            results.append(200)
        except HTTPException as error:
            results.append(error.status_code)

    threads = [threading.Thread(target=worker, args=(user_id,)) for user_id in user_ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


@pytest.fixture()
def slow_day(monkeypatch):
    set_clock(monkeypatch, NOON_KST)
    day = SlowDay()
    monkeypatch.setattr(main, "_vision_scan_counts", {datetime(2026, 10, 7).date(): day})
    return day


def test_concurrent_scans_stop_at_user_cap(slow_day):
    results = reserve_from_threads([1] * 40)

    assert slow_day.slow_writes == main.SCAN_USER_DAILY_MAX  # 틈을 벌리는 쓰기를 실제로 거쳤다
    assert results.count(200) == main.SCAN_USER_DAILY_MAX
    assert results.count(429) == 40 - main.SCAN_USER_DAILY_MAX
    assert slow_day == {1: main.SCAN_USER_DAILY_MAX}


def test_concurrent_scans_stop_at_server_cap(slow_day, monkeypatch):
    monkeypatch.setattr(main, "SCAN_DAILY_MAX", 5)

    results = reserve_from_threads(list(range(1, 41)))

    assert slow_day.slow_writes == 5
    assert results.count(200) == 5
    assert results.count(503) == 35
    assert sum(slow_day.values()) == 5


@pytest.mark.parametrize(
    "value, expected",
    [(None, None), ("", None), ("100", 100), (" 7 ", 7), ("1", 1)],
)
def test_parse_scan_daily_max(value, expected):
    assert main.parse_scan_daily_max(value) == expected


@pytest.mark.parametrize("value", ["  ", "0", "-1", "abc", "1.5", "1e3", "１００", "²", "10 0"])
def test_parse_scan_daily_max_rejects_other_values(value):
    # 공백만 있는 값은 compose 의 `:?` 를 통과하므로 '없음'으로 보지 않고 거부한다.
    with pytest.raises(ValueError, match="K_DPP_SCAN_DAILY_MAX"):
        main.parse_scan_daily_max(value)


def test_invalid_scan_daily_max_stops_startup():
    # 상수는 import 때 읽으므로 환경변수를 바꾼 별도 프로세스에서 본다.
    result = run_python("import main", K_DPP_SCAN_DAILY_MAX="unlimited")
    assert result.returncode != 0
    assert "K_DPP_SCAN_DAILY_MAX" in result.stderr
